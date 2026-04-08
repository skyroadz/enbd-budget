"""
Routes: /api/monthly-summary, /api/monthly-merchants, /api/all-time-merchants
"""
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from ..config import DB_PATH

router = APIRouter()


def _get_car_loan_payment(con: sqlite3.Connection, y: str, m: str) -> float:
    """Return the car loan payment amount for the given year/month, or 0."""
    con.row_factory = sqlite3.Row
    loan_row = con.execute(
        """
        SELECT next_payment_amount FROM loan_statements
        WHERE strftime('%Y', next_payment_date) = ?
          AND strftime('%m', next_payment_date) = ?
        LIMIT 1
        """,
        (y, m),
    ).fetchone()
    if loan_row:
        return float(loan_row["next_payment_amount"] or 0.0)

    latest = con.execute(
        """
        SELECT next_payment_amount, contract_signing_date, maturity_date
        FROM loan_statements ORDER BY statement_date DESC LIMIT 1
        """
    ).fetchone()
    if latest and latest["next_payment_amount"]:
        month_start = f"{y}-{m}-01"
        if latest["contract_signing_date"] < month_start <= latest["maturity_date"]:
            return float(latest["next_payment_amount"])
    return 0.0


def _get_ytd_car_payments(con: sqlite3.Connection, y: str, up_to_month: int) -> float:
    """Sum car loan payments for all months in year y up to up_to_month (inclusive)."""
    total = 0.0
    for mm in range(1, up_to_month + 1):
        ms = f"{mm:02d}"
        total += _get_car_loan_payment(con, y, ms)
    return round(total, 2)


@router.get("/api/monthly-summary")
def api_monthly_summary(
    year: Optional[str] = Query(None, description="YYYY — defaults to current year"),
    month: Optional[str] = Query(None, description="MM — defaults to current month"),
    card_scope: Optional[str] = Query(None, description="primary | supplementary | (empty = all)"),
):
    """
    Summary stats and category breakdown for the given month.
    Car loan payment is added to 'car' category and included in spend totals.
    txn_count and avg_per_txn are CC-only (exclude loan payments).
    """
    today = datetime.today()
    y = year or f"{today.year:04d}"
    m = (month or f"{today.month:02d}").zfill(2)
    ym_prefix = f"{y}-{m}%"

    scope_filter = card_scope if card_scope in ("primary", "supplementary") else None

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row

        # --- CC transactions for this month ---
        if scope_filter:
            rows = con.execute(
                """
                SELECT category, amount_aed, card_scope
                FROM transactions
                WHERE txn_date LIKE ?
                  AND card_scope = ?
                """,
                (ym_prefix, scope_filter),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT category, amount_aed, card_scope
                FROM transactions
                WHERE txn_date LIKE ?
                """,
                (ym_prefix,),
            ).fetchall()

        # --- Car loan payment ---
        include_loan = scope_filter is None or scope_filter == "primary"
        car_loan = _get_car_loan_payment(con, y, m) if include_loan else 0.0

        # --- YTD: sum CC spend + loan payments ---
        current_month_int = int(m)
        current_year_int = int(y)
        is_current_year = (current_year_int == today.year)
        ytd_up_to = min(current_month_int, today.month) if is_current_year else current_month_int

        if scope_filter:
            ytd_rows = con.execute(
                """
                SELECT amount_aed FROM transactions
                WHERE txn_date LIKE ?
                  AND card_scope = ?
                """,
                (f"{y}-%",  scope_filter),
            ).fetchall()
        else:
            ytd_rows = con.execute(
                """
                SELECT amount_aed FROM transactions
                WHERE txn_date LIKE ?
                """,
                (f"{y}-%",),
            ).fetchall()

        # Only count YTD txns up to selected month
        ytd_rows_filtered = con.execute(
            f"""
            SELECT amount_aed FROM transactions
            WHERE txn_date >= '{y}-01-01'
              AND txn_date <= '{y}-{m}-31'
              {"AND card_scope = '" + scope_filter + "'" if scope_filter else ""}
            """
        ).fetchall()

        ytd_loan = _get_ytd_car_payments(con, y, ytd_up_to) if include_loan else 0.0

    # Compute stats from CC rows
    total_spend = 0.0
    total_refunds = 0.0
    txn_count = 0
    primary_spend = 0.0
    primary_txn_count = 0
    supp_spend = 0.0
    supp_txn_count = 0
    cat_map: dict = {}

    for r in rows:
        amt = float(r["amount_aed"])
        scope = r["card_scope"]
        cat = str(r["category"])

        if amt > 0:
            total_spend += amt
            txn_count += 1
            cat_map[cat] = round(cat_map.get(cat, 0.0) + amt, 2)
            if scope == "primary":
                primary_spend += amt
                primary_txn_count += 1
            elif scope == "supplementary":
                supp_spend += amt
                supp_txn_count += 1
        else:
            total_refunds += (-amt)

    # Add car loan to totals and category map
    if car_loan:
        total_spend += car_loan
        cat_map["car"] = round(cat_map.get("car", 0.0) + car_loan, 2)
        if include_loan:
            primary_spend += car_loan

    total_spend = round(total_spend, 2)
    total_refunds = round(total_refunds, 2)
    net_spend = round(total_spend - total_refunds, 2)
    primary_spend = round(primary_spend, 2)
    supp_spend = round(supp_spend, 2)
    avg_per_txn = round(total_spend / txn_count, 2) if txn_count else 0.0

    # YTD spend (CC only, up to this month)
    ytd_cc = sum(float(r["amount_aed"]) for r in ytd_rows_filtered if float(r["amount_aed"]) > 0)
    ytd_spend = round(ytd_cc + ytd_loan, 2)

    categories = sorted(
        [{"category": cat, "total_spend": round(v, 2)} for cat, v in cat_map.items()],
        key=lambda x: x["total_spend"],
        reverse=True,
    )

    return {
        "year": y,
        "month": m,
        "stats": [{
            "total_spend":       total_spend,
            "txn_count":         txn_count,
            "avg_per_txn":       avg_per_txn,
            "total_refunds":     total_refunds,
            "net_spend":         net_spend,
            "ytd_spend":         ytd_spend,
            "primary_spend":     primary_spend,
            "primary_txn_count": primary_txn_count,
            "supp_spend":        supp_spend,
            "supp_txn_count":    supp_txn_count,
        }],
        "categories": categories,
    }


@router.get("/api/monthly-merchants")
def api_monthly_merchants(
    year: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    card_scope: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=200),
):
    """Top merchants by spend for the given month."""
    today = datetime.today()
    y = year or f"{today.year:04d}"
    m = (month or f"{today.month:02d}").zfill(2)
    ym_prefix = f"{y}-{m}%"
    scope_filter = card_scope if card_scope in ("primary", "supplementary") else None

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        if scope_filter:
            rows = con.execute(
                """
                SELECT merchant, category,
                       ROUND(SUM(amount_aed), 2) AS total_spend,
                       COUNT(*) AS txn_count
                FROM transactions
                WHERE txn_date LIKE ?
                  AND amount_aed > 0
                  AND card_scope = ?
                GROUP BY merchant, category
                ORDER BY total_spend DESC
                LIMIT ?
                """,
                (ym_prefix, scope_filter, limit),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT merchant, category,
                       ROUND(SUM(amount_aed), 2) AS total_spend,
                       COUNT(*) AS txn_count
                FROM transactions
                WHERE txn_date LIKE ?
                  AND amount_aed > 0
                GROUP BY merchant, category
                ORDER BY total_spend DESC
                LIMIT ?
                """,
                (ym_prefix, limit),
            ).fetchall()

    return {"year": y, "month": m, "merchants": [dict(r) for r in rows]}


@router.get("/api/all-time-merchants")
def api_all_time_merchants(
    card_scope: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=500),
):
    """Top merchants by total spend across all time."""
    scope_filter = card_scope if card_scope in ("primary", "supplementary") else None

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        if scope_filter:
            rows = con.execute(
                """
                SELECT merchant, category,
                       ROUND(SUM(amount_aed), 2) AS total_spend,
                       COUNT(*) AS txn_count
                FROM transactions
                WHERE amount_aed > 0
                  AND card_scope = ?
                GROUP BY merchant, category
                ORDER BY total_spend DESC
                LIMIT ?
                """,
                (scope_filter, limit),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT merchant, category,
                       ROUND(SUM(amount_aed), 2) AS total_spend,
                       COUNT(*) AS txn_count
                FROM transactions
                WHERE amount_aed > 0
                GROUP BY merchant, category
                ORDER BY total_spend DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    return {"merchants": [dict(r) for r in rows]}
