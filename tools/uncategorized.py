import os, sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", Path("data") / "state.db"))

with sqlite3.connect(DB_PATH) as con:
    cur = con.execute("""
      SELECT merchant,
             COUNT(*) AS txn_count,
             ROUND(SUM(amount_aed), 2) AS total_aed
      FROM transactions
      WHERE category = 'uncategorized'
      GROUP BY merchant
      ORDER BY total_aed DESC, txn_count DESC
      LIMIT 500
    """)
    rows = cur.fetchall()

print(f"Uncategorized merchants: {len(rows)} (top 500 shown)\n")
for m, c, t in rows:
    print(f"{t:>10} AED | {c:>4} txns | {m}")