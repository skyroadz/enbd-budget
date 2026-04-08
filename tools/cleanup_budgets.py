"""
Show budget categories with no matching transactions, then optionally delete them.

Usage:
    python tools/cleanup_budgets.py          # dry-run: list orphan categories
    python tools/cleanup_budgets.py --delete # actually delete them
"""
import os, sys, sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", Path("data") / "state.db"))
delete = "--delete" in sys.argv

with sqlite3.connect(DB_PATH) as con:
    con.row_factory = sqlite3.Row

    # All budget categories and their all-time spend
    rows = con.execute("""
        SELECT
            b.category,
            b.monthly_aed AS budget_aed,
            COALESCE(SUM(CASE WHEN t.amount_aed > 0 THEN t.amount_aed END), 0) AS total_spent,
            COUNT(t.id) AS txn_count
        FROM budgets b
        LEFT JOIN transactions t ON t.category = b.category
        GROUP BY b.category
        ORDER BY total_spent ASC, b.category
    """).fetchall()

    if not rows:
        print("No budget categories found.")
        sys.exit(0)

    orphans = [r for r in rows if r["txn_count"] == 0]
    has_txns = [r for r in rows if r["txn_count"] > 0]

    print("=== Budget categories WITH transactions ===")
    for r in has_txns:
        print(f"  {r['category']:<25}  budget={r['budget_aed']:>8.0f} AED  "
              f"spent={r['total_spent']:>10.0f} AED  txns={r['txn_count']}")

    print(f"\n=== Budget categories with NO transactions ({len(orphans)}) ===")
    if not orphans:
        print("  None — everything looks clean.")
        sys.exit(0)

    for r in orphans:
        print(f"  {r['category']:<25}  budget={r['budget_aed']:>8.0f} AED")

    if not delete:
        print(f"\nDry run — {len(orphans)} orphan(s) found. Re-run with --delete to remove them.")
        sys.exit(0)

    cats = [r["category"] for r in orphans]
    placeholders = ",".join("?" * len(cats))
    con.execute(f"DELETE FROM budgets WHERE category IN ({placeholders})", cats)
    con.commit()
    print(f"\nDeleted {len(orphans)} orphan budget category/ies: {', '.join(cats)}")
