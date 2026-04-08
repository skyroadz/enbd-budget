"""
Rules engine: load and cache rules.yaml, merchant cleanup, categorisation, DB recategorisation.
"""
import logging
import re
import sqlite3
from typing import Any, Dict

import yaml

from .config import DB_PATH, RULES_PATH, ML_CONFIDENCE_THRESHOLD
from . import ml_model

log = logging.getLogger(__name__)

_rules_cache: Dict[str, Any] = {}
_rules_mtime: float = 0.0
# Pre-computed upper-cased categories_by_merchant so categorize() doesn't rebuild per call
_by_merchant_upper: Dict[str, str] = {}


def _validate_rules(rules: Dict[str, Any]) -> None:
    """Log warnings for invalid regex patterns so bugs surface immediately."""
    for rule in rules.get("merchant_aliases") or []:
        m = rule.get("match") or ""
        try:
            re.compile(m)
        except re.error as exc:
            log.warning("Invalid merchant_aliases regex %r: %s", m, exc)
    for pat in (rules.get("merchant_cleanup") or {}).get("remove_regex") or []:
        try:
            re.compile(str(pat))
        except re.error as exc:
            log.warning("Invalid remove_regex pattern %r: %s", pat, exc)


def load_rules() -> Dict[str, Any]:
    """
    Return cached rules, refreshing from disk only when rules.yaml has changed.

    When rules change, all existing DB rows are auto-recategorised so Prometheus
    metrics reflect the new rules on the very next scrape.
    """
    global _rules_cache, _rules_mtime, _by_merchant_upper

    try:
        mtime = RULES_PATH.stat().st_mtime
    except FileNotFoundError:
        return {}

    if mtime == _rules_mtime:
        return _rules_cache

    rules = yaml.safe_load(RULES_PATH.read_text()) or {}
    prev_mtime = _rules_mtime
    _rules_cache = rules
    _rules_mtime = mtime
    _by_merchant_upper = {k.upper(): v for k, v in (rules.get("categories_by_merchant") or {}).items()}
    log.info("Reloaded rules.yaml (mtime changed)")
    _validate_rules(rules)

    if prev_mtime != 0.0:
        updated = recategorize_db()
        log.info("Auto-recategorized %d rows after rules change", updated)

    return rules


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def apply_merchant_cleanup(d: str, rules: Dict[str, Any]) -> str:
    """
    Generic normalisation to remove common noise that causes merchant duplication.
    Controlled by rules.yaml: merchant_cleanup section.
    """
    cleanup = rules.get("merchant_cleanup") or {}

    d = normalize_spaces(d).upper()

    # Replace dots with spaces early so "ST.REGIS" → "ST REGIS"
    d = d.replace(".", " ")
    d = normalize_spaces(d)

    # Strip prefixes multi-pass: repeat until stable so compound prefixes like
    # "*SQ *MERCHANT" (leading "*" peeled first, then "SQ *") are fully removed.
    prefixes = [str(p).upper() for p in (cleanup.get("strip_prefixes") or []) if str(p).strip()]
    changed = True
    while changed:
        changed = False
        for pref_u in prefixes:
            if d.startswith(pref_u):
                d = d[len(pref_u):].strip()
                changed = True
                break

    # Remove trailing FX amount/currency (e.g., "21.00 USD")
    d = re.sub(r"\s+\d+(?:\.\d+)?\s+[A-Z]{3}\s*$", "", d).strip()

    # Strip trailing tokens listed in rules (e.g., "DUBAI", "ARE")
    for tok in (cleanup.get("strip_trailing_tokens") or []):
        tok_u = str(tok).upper()
        if not tok_u:
            continue
        if d.endswith(" " + tok_u):
            d = d[: -(len(tok_u) + 1)].strip()
        elif d == tok_u:
            d = ""

    # Apply ordered regex removals
    for pat in (cleanup.get("remove_regex") or []):
        try:
            d = re.sub(str(pat), "", d, flags=re.IGNORECASE).strip()
        except re.error:
            pass  # ignore invalid regex rather than breaking /metrics scraping

    d = normalize_spaces(d)
    return d


def merchant_from_description(desc: str, rules: Dict[str, Any]) -> str:
    """
    Merchant normalisation + canonicalisation:
    1. Cleanup (prefixes, trailing tokens, regex removals)
    2. Apply alias rules (regex → canonical name)
    """
    d = apply_merchant_cleanup(desc, rules)
    if not d:
        return "UNKNOWN"

    aliases = rules.get("merchant_aliases") or []
    for rule in aliases:
        m = (rule.get("match") or "").strip()
        canon = (rule.get("canonical") or "").strip()
        if not m or not canon:
            continue
        try:
            if re.match(m, d, flags=re.IGNORECASE):
                return canon.upper()
        except re.error:
            continue

    return d.upper()


def categorize(merchant: str, desc: str, rules: Dict[str, Any]) -> tuple:
    """
    Category precedence:
      1. categories_by_merchant — exact canonical merchant match (strongest)
      2. categories[] — substring match against canonical merchant OR raw description
      3. ML model — if available and confidence >= ML_CONFIDENCE_THRESHOLD
      4. uncategorized

    Returns (category: str, ml_confidence: float | None).
    ml_confidence is None when the category was determined by rules (not ML).
    """
    merchant_u = (merchant or "").upper()
    desc_u = (desc or "").upper()

    if merchant_u in _by_merchant_upper:
        return _by_merchant_upper[merchant_u], None

    for cat, patterns in (rules.get("categories") or {}).items():
        for p in patterns:
            p_u = str(p).upper()
            if p_u in merchant_u or p_u in desc_u:
                return cat, None

    # Rules didn't match — try ML
    ml_cat, ml_conf = ml_model.predict(merchant_u)
    if ml_cat and ml_conf >= ML_CONFIDENCE_THRESHOLD:
        return ml_cat, ml_conf

    return "uncategorized", ml_conf if ml_conf else None


def audit_rules() -> dict:
    """
    Compare rules-only categorization against manually-locked transactions.
    Returns merchants where the rules would assign a different category than
    what the user locked — split into 'wrong_rule' and 'no_rule' groups.
    """
    rules = load_rules()
    by_merch = {k.upper(): v for k, v in (rules.get("categories_by_merchant") or {}).items()}

    def rules_only(merchant: str) -> str:
        m_u = merchant.upper()
        if m_u in by_merch:
            return by_merch[m_u]
        for cat, patterns in (rules.get("categories") or {}).items():
            for p in patterns:
                if str(p).upper() in m_u:
                    return cat
        return "uncategorized"

    wrong_rule = []
    no_rule    = []
    correct    = 0

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT merchant, category, COUNT(*) AS cnt,
                   ROUND(SUM(amount_aed), 2) AS total_aed
            FROM transactions
            WHERE category_locked = 1
              AND merchant IS NOT NULL AND merchant != '' AND merchant != 'UNKNOWN'
            GROUP BY merchant, category
            ORDER BY cnt DESC
        """).fetchall()

    for row in rows:
        merchant   = row["merchant"]
        locked_cat = row["category"]
        rule_cat   = rules_only(merchant)
        entry = {"merchant": merchant, "locked": locked_cat, "rule": rule_cat,
                 "txn_count": row["cnt"], "total_aed": row["total_aed"] or 0.0}
        if rule_cat == locked_cat:
            correct += 1
        elif rule_cat == "uncategorized":
            no_rule.append(entry)
        else:
            wrong_rule.append(entry)

    return {"wrong_rule": wrong_rule, "no_rule": no_rule, "correct_count": correct}


def recategorize_db() -> int:
    """
    Recompute merchant + category for all existing rows using current rules.yaml.
    Returns number of updated rows.
    """
    rules = load_rules()
    updated = 0

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, description_raw FROM transactions WHERE category_locked = 0"
        ).fetchall()

        for r in rows:
            desc = r["description_raw"]
            new_merchant = merchant_from_description(desc, rules)
            new_category, ml_conf = categorize(new_merchant, desc, rules)

            res = con.execute(
                "UPDATE transactions SET merchant=?, category=?, ml_confidence=? "
                "WHERE id=? AND category_locked=0 AND (merchant<>? OR category<>?)",
                (new_merchant, new_category, ml_conf, r["id"], new_merchant, new_category),
            )
            updated += res.rowcount

        con.commit()

    return updated
