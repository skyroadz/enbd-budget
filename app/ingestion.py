"""
Credit card PDF parsing and incremental ingestion into SQLite.
Aggregation helpers for Prometheus metrics.
"""
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

from .config import (
    DB_PATH, STATEMENTS_DIR,
    TXN_RE, FX_IN_DESC_RE, AED_RATE_LINE_RE, STOP_RE, SUPP_RE, INSTALLMENT_RE,
)
from .db import should_ingest, mark_ingested, upsert_rows, year_month_of
from .rules import load_rules, normalize_spaces, merchant_from_description, categorize

log = logging.getLogger(__name__)


def parse_pdf_lines(pdf_path: Path) -> List[str]:
    lines: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for ln in text.splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(ln)
    return lines


def parse_statement(pdf_path: Path) -> List[Dict[str, Any]]:
    rules = load_rules()
    lines = parse_pdf_lines(pdf_path)

    rows: List[Dict[str, Any]] = []
    card_scope = "primary"

    i = 0
    while i < len(lines):
        ln = lines[i]

        if STOP_RE.match(ln):
            break

        if SUPP_RE.match(ln):
            card_scope = "supplementary"
            i += 1
            continue

        # Skip installment block region
        if INSTALLMENT_RE.match(ln):
            i += 1
            while i < len(lines) and not TXN_RE.match(lines[i]) and not STOP_RE.match(lines[i]) and not SUPP_RE.match(lines[i]):
                i += 1
            continue

        m = TXN_RE.match(ln)
        if not m:
            i += 1
            continue

        txn_date  = datetime.strptime(m.group("txn_date"),  "%d/%m/%Y").date().isoformat()
        post_date = datetime.strptime(m.group("post_date"), "%d/%m/%Y").date().isoformat()
        desc = normalize_spaces(m.group("desc").strip())

        amount_aed = float(m.group("amount").replace(",", ""))
        is_credit = 1 if m.group("cr") else 0
        if is_credit:
            amount_aed = -amount_aed

        orig_ccy: Optional[str] = None
        orig_amount: Optional[float] = None

        # FX case: description ends with "<amount> <CCY>"
        fxm = FX_IN_DESC_RE.match(desc)
        if fxm:
            orig_amount = float(fxm.group("orig_amount"))
            orig_ccy = fxm.group("orig_ccy")

            # Next line often is "(1 AED = ...)" then AED amount line
            j = i + 1
            if j < len(lines) and AED_RATE_LINE_RE.match(lines[j]):
                if j + 1 < len(lines):
                    aed_line = lines[j + 1].strip()
                    aed_is_credit = aed_line.endswith("CR")
                    if aed_is_credit:
                        aed_line = aed_line[:-2].strip()
                    if re.match(r"^[\d,]+\.\d{2}$", aed_line):
                        amount_aed = float(aed_line.replace(",", ""))
                        if aed_is_credit:
                            amount_aed = -amount_aed
                            is_credit = 1
                        else:
                            is_credit = 0
                        i = j + 1

        ignore = rules.get("ignore_descriptions") or []
        if any(str(x).upper() in desc.upper() for x in ignore):
            i += 1
            continue

        merchant = merchant_from_description(desc, rules)
        category, ml_confidence = categorize(merchant, desc, rules)

        rows.append({
            "txn_date":        txn_date,
            "post_date":       post_date,
            "description_raw": desc,
            "merchant":        merchant,
            "category":        category,
            "ml_confidence":   ml_confidence,
            "amount_aed":      amount_aed,
            "is_credit":       is_credit,
            "card_scope":      card_scope,
            "orig_currency":   orig_ccy,
            "orig_amount":     orig_amount,
            "statement_file":  pdf_path.name,
        })

        i += 1

    return rows


def ingest_incremental() -> int:
    """
    Ingest only new/changed credit card PDFs using a single shared DB connection.
    Returns number of files processed on this call.
    """
    STATEMENTS_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(STATEMENTS_DIR.glob("*.pdf"))

    ingested = 0
    with sqlite3.connect(DB_PATH) as con:
        for p in pdfs:
            if not should_ingest(con, p):
                continue
            rows = parse_statement(p)
            inserted, skipped = upsert_rows(con, rows)
            mark_ingested(con, p)
            con.commit()
            ingested += 1
            log.info("Ingested %s: %d rows inserted, %d duplicates skipped", p.name, inserted, skipped)
    return ingested


def compute_category_aggregates() -> Dict[Tuple[str, str, str, str], Dict[str, float]]:
    """Aggregate spend by (year, month, category, card_scope)."""
    agg: Dict[Tuple[str, str, str, str], Dict[str, float]] = {}

    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("SELECT txn_date, category, amount_aed, card_scope FROM transactions")
        for txn_date, category, amount_aed, card_scope in cur.fetchall():
            y, m = year_month_of(txn_date)
            key = (y, m, str(category), str(card_scope))
            if key not in agg:
                agg[key] = {"total": 0.0, "count": 0.0, "debit_count": 0.0, "refunds": 0.0}
            amt = float(amount_aed)
            agg[key]["total"] += amt
            agg[key]["count"] += 1.0
            if amt < 0:
                agg[key]["refunds"] += (-amt)
            else:
                agg[key]["debit_count"] += 1.0

    for k in list(agg.keys()):
        agg[k]["total"]   = round(agg[k]["total"],   2)
        agg[k]["refunds"] = round(agg[k]["refunds"], 2)

    # Inject car loan payments as synthetic 'car' / 'primary' entries
    with sqlite3.connect(DB_PATH) as loan_con:
        latest_loan = loan_con.execute("""
            SELECT next_payment_amount, contract_signing_date, maturity_date
            FROM loan_statements ORDER BY statement_date DESC LIMIT 1
        """).fetchone()
        if latest_loan and latest_loan[0] and latest_loan[1] and latest_loan[2]:
            # Per-month specific amounts (from statements that have next_payment_date)
            specific = {
                (r[0], r[1]): r[2]
                for r in loan_con.execute("""
                    SELECT strftime('%Y', next_payment_date),
                           strftime('%m', next_payment_date),
                           next_payment_amount
                    FROM loan_statements WHERE next_payment_date IS NOT NULL
                """).fetchall()
            }
            fixed_payment = latest_loan[0]
            # First payment = month after contract signing
            cy, cm = int(latest_loan[1][:4]), int(latest_loan[1][5:7])
            cm += 1
            if cm > 12:
                cm, cy = 1, cy + 1
            my, mm = int(latest_loan[2][:4]), int(latest_loan[2][5:7])
            y, m = cy, cm
            while (y, m) <= (my, mm):
                ys, ms = f"{y:04d}", f"{m:02d}"
                payment = specific.get((ys, ms), fixed_payment)
                key = (ys, ms, "car", "primary")
                if key not in agg:
                    agg[key] = {"total": 0.0, "count": 0.0, "debit_count": 0.0, "refunds": 0.0}
                agg[key]["total"]       = round(agg[key]["total"] + payment, 2)
                agg[key]["count"]       += 1.0
                agg[key]["debit_count"] += 1.0
                m += 1
                if m > 12:
                    m, y = 1, y + 1

    return agg


def compute_merchant_aggregates_all() -> Dict[Tuple[str, str, str, str, str], float]:
    """Aggregate spend by (year, month, category, merchant, card_scope) for all merchants."""
    per: Dict[Tuple[str, str, str, str, str], float] = {}
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("SELECT txn_date, merchant, category, amount_aed, card_scope FROM transactions")
        for txn_date, merchant, category, amount_aed, card_scope in cur.fetchall():
            y, m = year_month_of(txn_date)
            key = (y, m, str(category), str(merchant), str(card_scope))
            per[key] = per.get(key, 0.0) + float(amount_aed)

    for k in list(per.keys()):
        per[k] = round(per[k], 2)

    return per
