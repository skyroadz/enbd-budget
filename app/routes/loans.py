"""
Routes: GET /api/loans
"""
import sqlite3

from fastapi import APIRouter

from ..config import DB_PATH

router = APIRouter()


@router.get("/api/loans")
def api_loans():
    """
    All ingested loan statements, most recent first.
    Each entry includes computed paid_principal, paid_profit, and total_paid
    (derived from finance_amount / total_profit_amount minus outstanding balances).
    """
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT * FROM loan_statements
            ORDER BY statement_date DESC
        """).fetchall()

    result = []
    for r in rows:
        d  = dict(r)
        fa = d["finance_amount"]        or 0
        tp = d["total_profit_amount"]   or 0
        op = d["outstanding_principal"] or 0
        rp = d["remaining_profit"]      or 0
        d["paid_principal"] = round(fa - op, 2)
        d["paid_profit"]    = round(tp - rp, 2)
        d["total_paid"]     = round(d["paid_principal"] + d["paid_profit"], 2)
        result.append(d)

    return {"loans": result}
