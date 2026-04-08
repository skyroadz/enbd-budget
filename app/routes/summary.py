"""
Routes: /api/summary/monthly, /api/summary/merchants, /api/summary/merchant-monthly,
        /api/merchants, /api/bank-history, /api/bank-monthly-totals
"""
import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from ..config import DB_PATH

router = APIRouter()


def _months_back_cutoff(n: int) -> str:
    """Return ISO date string for the first day of the month n months ago."""
    today = date.today()
    idx = today.year * 12 + today.month - 1 - n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}-01"


@router.get("/api/summary/monthly")
def api_summary_monthly(months_back: Optional[int] = Query(None, ge=1, le=120)):
    """Monthly credit card spend aggregated by category. Excludes credits/refunds."""
    params: List[Any] = []
    date_filter = ""
    if months_back is not None:
        date_filter = "AND txn_date >= ?"
        params.append(_months_back_cutoff(months_back))

    sql = f"""
        SELECT
            strftime('%Y', txn_date) AS year,
            strftime('%m', txn_date) AS month,
            category,
            ROUND(SUM(amount_aed), 2) AS total
        FROM transactions
        WHERE amount_aed > 0
          {date_filter}
        GROUP BY year, month, category
        ORDER BY year, month, category
    """
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()

    months_dict: Dict[str, Dict] = {}
    category_totals: Dict[str, float] = {}
    grand_total = 0.0

    for r in rows:
        ym = f"{r['year']}-{r['month']}"
        if ym not in months_dict:
            months_dict[ym] = {"year": r["year"], "month": r["month"], "ym": ym, "categories": {}, "total": 0.0}
        months_dict[ym]["categories"][r["category"]] = r["total"]
        months_dict[ym]["total"] = round(months_dict[ym]["total"] + r["total"], 2)
        category_totals[r["category"]] = round(category_totals.get(r["category"], 0.0) + r["total"], 2)
        grand_total = round(grand_total + r["total"], 2)

    return {
        "months": sorted(months_dict.values(), key=lambda x: x["ym"]),
        "category_totals": category_totals,
        "grand_total": grand_total,
    }


@router.get("/api/summary/merchants")
def api_summary_merchants(
    months_back: Optional[int] = Query(None, ge=1, le=120),
    limit:       int           = Query(10, ge=1, le=50),
):
    """Top merchants by total spend. Excludes credits/refunds."""
    params: List[Any] = []
    date_filter = ""
    if months_back is not None:
        date_filter = "AND txn_date >= ?"
        params.append(_months_back_cutoff(months_back))

    sql = f"""
        SELECT
            merchant,
            MAX(category) AS category,
            ROUND(SUM(amount_aed), 2) AS total_aed,
            COUNT(*) AS txn_count
        FROM transactions
        WHERE amount_aed > 0
          {date_filter}
        GROUP BY merchant
        ORDER BY total_aed DESC
        LIMIT ?
    """
    params.append(limit)

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()

    return {"merchants": [dict(r) for r in rows]}


@router.get("/api/merchants")
def api_merchants(q: str = Query("", max_length=100)):
    """Autocomplete: distinct merchant names containing the query string."""
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT DISTINCT merchant FROM transactions WHERE UPPER(merchant) LIKE ? ORDER BY merchant LIMIT 20",
            (f"%{q.upper()}%",),
        ).fetchall()
    return {"merchants": [r[0] for r in rows if r[0]]}


@router.get("/api/summary/merchant-monthly")
def api_summary_merchant_monthly(
    merchant:    str           = Query(..., min_length=1, max_length=200),
    months_back: Optional[int] = Query(None, ge=1, le=120),
):
    """Monthly spend totals for a specific merchant."""
    params: List[Any] = [merchant]
    date_filter = ""
    if months_back is not None:
        date_filter = "AND txn_date >= ?"
        params.append(_months_back_cutoff(months_back))

    sql = f"""
        SELECT
            strftime('%Y', txn_date) AS year,
            strftime('%m', txn_date) AS month,
            ROUND(SUM(amount_aed), 2) AS total_aed,
            COUNT(*) AS txn_count
        FROM transactions
        WHERE merchant = ? AND amount_aed > 0
          {date_filter}
        GROUP BY year, month
        ORDER BY year, month
    """
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()

    return {
        "merchant": merchant,
        "months": [
            {
                "ym":        f"{r['year']}-{r['month']}",
                "year":      r["year"],
                "month":     r["month"],
                "total_aed": r["total_aed"],
                "txn_count": r["txn_count"],
            }
            for r in rows
        ],
    }


@router.get("/api/bank-history")
def api_bank_history(months_back: Optional[int] = Query(None, ge=1, le=120)):
    """
    Monthly income, savings balance, and savings received.
    savings_balance is auto-derived from the last bank_transactions balance for the
    savings account each month; monthly_config overrides it if manually set.
    """
    params: List[Any] = []
    date_filter_cfg = ""
    date_filter_txn = ""
    if months_back is not None:
        cutoff = _months_back_cutoff(months_back)
        cutoff_y, cutoff_m = cutoff[:4], cutoff[5:7]
        date_filter_cfg = "AND (year > ? OR (year = ? AND CAST(month AS INTEGER) >= CAST(? AS INTEGER)))"
        date_filter_txn = "AND txn_date >= ?"
        params_cfg = [cutoff_y, cutoff_y, cutoff_m]
        params_txn = [cutoff]
    else:
        params_cfg = []
        params_txn = []

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row

        cfg_rows = con.execute(f"""
            SELECT year, month, key, amount_aed
            FROM monthly_config
            WHERE key IN ('income', 'savings_balance', 'savings_actual')
            {date_filter_cfg}
            ORDER BY year, month, key
        """, params_cfg).fetchall()

        # Last savings balance per month from bank_transactions
        savings_rows = con.execute(f"""
            SELECT
                strftime('%Y', txn_date) AS year,
                strftime('%m', txn_date) AS month,
                balance
            FROM bank_transactions
            WHERE account = 'savings'
            {date_filter_txn}
            GROUP BY year, month
            HAVING txn_date = MAX(txn_date)
            ORDER BY year, month
        """, params_txn).fetchall()

    months_dict: Dict[str, Dict] = {}

    # Seed with auto-derived savings balances
    for r in savings_rows:
        ym = f"{r['year']}-{r['month']}"
        months_dict[ym] = {"ym": ym, "year": r["year"], "month": r["month"], "savings_balance": r["balance"]}

    # Apply manual config (income, savings_actual always; savings_balance overrides auto)
    for r in cfg_rows:
        ym = f"{r['year']}-{r['month']}"
        if ym not in months_dict:
            months_dict[ym] = {"ym": ym, "year": r["year"], "month": r["month"]}
        months_dict[ym][r["key"]] = r["amount_aed"]

    return {"months": sorted(months_dict.values(), key=lambda x: x["ym"])}


@router.get("/api/bank-monthly-totals")
def api_bank_monthly_totals(months_back: Optional[int] = Query(None, ge=1, le=120)):
    """
    Monthly credit and debit totals per account from bank_transactions.
    Returns rows: [{account, year, month, total_in, total_out}]
    """
    params: List[Any] = []
    date_filter = ""
    if months_back is not None:
        cutoff = _months_back_cutoff(months_back)
        date_filter = "WHERE txn_date >= ?"
        params.append(cutoff)

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(f"""
            SELECT
                account,
                strftime('%Y', txn_date) AS year,
                strftime('%m', txn_date) AS month,
                SUM(CASE WHEN is_credit = 1 THEN amount ELSE 0 END) AS total_in,
                SUM(CASE WHEN is_credit = 0 THEN amount ELSE 0 END) AS total_out
            FROM bank_transactions
            {date_filter}
            GROUP BY account, year, month
            ORDER BY year, month, account
        """, params).fetchall()

    return {"rows": [
        {**dict(r), "ym": f"{r['year']}-{r['month']}"}
        for r in rows
    ]}
