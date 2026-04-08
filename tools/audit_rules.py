"""
Audit rules.yaml against manually-corrected transactions.

Finds merchants where category_locked=1 (user manually set the category)
but the current rules.yaml would assign a different category — meaning the
rule is wrong, missing, or needs an override.

Usage:
    python tools/audit_rules.py [--db path/to/state.db] [--rules path/to/rules.yaml]

Outputs three sections:
  1. WRONG RULE    — a rule fires but gives the wrong answer
  2. NO RULE MATCH — rules fall through; user-set category is the right one to codify
  3. ALREADY CORRECT — rules agree with the locked category (sanity check)
"""
import argparse
import re
import sqlite3
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--db",           default="data/state.db", help="Path to state.db")
parser.add_argument("--rules",        default="rules.yaml",    help="Path to rules.yaml")
parser.add_argument("--show-correct", action="store_true",     help="Also list already-correct merchants")
args = parser.parse_args()

DB_PATH    = Path(args.db)
RULES_PATH = Path(args.rules)

if not DB_PATH.exists():
    raise SystemExit(f"DB not found: {DB_PATH}")
if not RULES_PATH.exists():
    raise SystemExit(f"rules.yaml not found: {RULES_PATH}")

# ---------------------------------------------------------------------------
# Load rules (mirrors rules.py logic, no app imports needed)
# ---------------------------------------------------------------------------
rules = yaml.safe_load(RULES_PATH.read_text()) or {}
by_merchant_upper = {k.upper(): v for k, v in (rules.get("categories_by_merchant") or {}).items()}


def rules_categorize(merchant: str) -> str:
    """Rules-only categorization (no ML). Returns category string."""
    m_u = merchant.upper()
    if m_u in by_merchant_upper:
        return by_merchant_upper[m_u]
    for cat, patterns in (rules.get("categories") or {}).items():
        for p in patterns:
            if str(p).upper() in m_u:
                return cat
    return "uncategorized"


# ---------------------------------------------------------------------------
# Query locked transactions
# ---------------------------------------------------------------------------
with sqlite3.connect(DB_PATH) as con:
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT merchant, category, COUNT(*) AS cnt, SUM(amount) AS total
        FROM transactions
        WHERE category_locked = 1
          AND merchant IS NOT NULL
          AND merchant != ''
          AND merchant != 'UNKNOWN'
        GROUP BY merchant, category
        ORDER BY cnt DESC
    """).fetchall()

# ---------------------------------------------------------------------------
# Compare rules vs locked category
# ---------------------------------------------------------------------------
wrong_rule = []   # rule fires but gives wrong answer
no_rule    = []   # no rule matches at all
correct    = []   # rules already agree

for row in rows:
    merchant   = row["merchant"]
    locked_cat = row["category"]
    rule_cat   = rules_categorize(merchant)
    cnt        = row["cnt"]
    total      = row["total"] or 0.0

    entry = (merchant, locked_cat, rule_cat, cnt, total)
    if rule_cat == locked_cat:
        correct.append(entry)
    elif rule_cat == "uncategorized":
        no_rule.append(entry)
    else:
        wrong_rule.append(entry)

wrong_rule.sort(key=lambda x: -x[3])
no_rule.sort(key=lambda x: -x[3])
correct.sort(key=lambda x: -x[3])

# ---------------------------------------------------------------------------
# Print
# ---------------------------------------------------------------------------
W = 42  # merchant column width


def section(title, count):
    bar = "=" * 80
    print(f"\n{bar}")
    print(f"  {title}  ({count} merchants)")
    print(bar)
    print(f"{'MERCHANT':<{W}}  {'LOCKED→':>14}  {'RULES→':>14}  {'TXN':>5}  {'AED':>10}")
    print("-" * 80)


def row_line(merchant, locked, rule, cnt, total):
    m = (merchant[:W - 1] + "…") if len(merchant) >= W else merchant
    print(f"{m:<{W}}  {locked:>14}  {rule:>14}  {cnt:>5}  {total:>10.2f}")


section("WRONG RULE  — fix or add an override in rules.yaml", len(wrong_rule))
for r in wrong_rule:
    row_line(*r)

section("NO RULE MATCH — consider adding to rules.yaml", len(no_rule))
for r in no_rule:
    row_line(*r)

print(f"\n{'=' * 80}")
print(f"  ALREADY CORRECT — {len(correct)} merchants (rules agree with locked category)")
print(f"{'=' * 80}")

if args.show_correct:
    section("ALREADY CORRECT", len(correct))
    for r in correct:
        row_line(*r)

print(f"\nSummary: {len(wrong_rule)} wrong rules  |  {len(no_rule)} missing rules  |  {len(correct)} correct\n")
