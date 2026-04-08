"""
Routes: /api/budget (CRUD), /api/monthly-config (CRUD)
"""
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import DB_PATH

router = APIRouter()

_ALLOWED_CONFIG_KEYS = {"income", "savings_actual", "savings_balance", "wife_income", "annual_rent"}


# ---------------------------------------------------------------------------
# Budget endpoints
# ---------------------------------------------------------------------------

class BudgetIn(BaseModel):
    category:   str   = Field(..., min_length=1, max_length=100)
    monthly_aed: float = Field(..., gt=0)


@router.post("/api/budget", status_code=200)
def api_budget_upsert(body: BudgetIn):
    """Create or update a monthly budget limit for a category."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO budgets (category, monthly_aed) VALUES (?, ?) "
            "ON CONFLICT(category) DO UPDATE SET monthly_aed=excluded.monthly_aed",
            (body.category, body.monthly_aed),
        )
        con.commit()
    return {"category": body.category, "monthly_aed": body.monthly_aed}


@router.delete("/api/budget/{category}", status_code=200)
def api_budget_delete(category: str):
    """Remove the budget limit for a category."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM budgets WHERE category = ?", (category,))
        con.commit()
    return {"deleted": category}


@router.get("/api/budget")
def api_budget_status(
    year:  Optional[str] = Query(None, description="YYYY — defaults to current year"),
    month: Optional[str] = Query(None, description="MM — defaults to current month"),
):
    """
    Spend vs budget for all categories for the given month.
    Returns every category that has a budget OR has spend in that month.
    """
    today = datetime.today()
    y = year or f"{today.year:04d}"
    m = (month or f"{today.month:02d}").zfill(2)
    ym_prefix = f"{y}-{m}%"

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row

        budgets: Dict[str, float] = {
            r["category"]: r["monthly_aed"]
            for r in con.execute("SELECT category, monthly_aed FROM budgets").fetchall()
        }

        spend_rows = con.execute(
            """
            SELECT category, ROUND(SUM(amount_aed), 2) AS spent
            FROM transactions
            WHERE amount_aed > 0
              AND txn_date LIKE ?
            GROUP BY category
            """,
            (ym_prefix,),
        ).fetchall()

        cfg_rows = con.execute(
            "SELECT key, amount_aed FROM monthly_config WHERE year=? AND month=?",
            (y, m),
        ).fetchall()

        # Annual rent: most recent entry on or before the current year+month.
        # year||month gives a comparable 6-char string (e.g. "202503").
        annual_rent_row = con.execute(
            """
            SELECT year, month, amount_aed FROM monthly_config
            WHERE key = 'annual_rent' AND year || month <= ? || ?
            ORDER BY year DESC, month DESC LIMIT 1
            """,
            (y, m),
        ).fetchone()

        # Car loan payment for the requested month.
        # First try: a statement whose next_payment_date falls in this month.
        # Fallback: if the month is within the loan term, use the latest statement's amount.
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
            car_loan_payment = loan_row["next_payment_amount"] or 0.0
        else:
            latest_loan = con.execute(
                """
                SELECT next_payment_amount, contract_signing_date, maturity_date
                FROM loan_statements
                ORDER BY statement_date DESC
                LIMIT 1
                """,
            ).fetchone()
            if latest_loan and latest_loan["next_payment_amount"]:
                month_start = f"{y}-{m}-01"
                if latest_loan["contract_signing_date"] < month_start <= latest_loan["maturity_date"]:
                    car_loan_payment = latest_loan["next_payment_amount"]
                else:
                    car_loan_payment = 0.0
            else:
                car_loan_payment = 0.0

    spend = {r["category"]: r["spent"] for r in spend_rows}
    cfg   = {r["key"]: r["amount_aed"] for r in cfg_rows}

    # Annual rent provision (1/12 of annual rent injected into 'rent' category spend)
    annual_rent  = annual_rent_row["amount_aed"] if annual_rent_row else None
    rent_year    = annual_rent_row["year"]        if annual_rent_row else None
    rent_month   = annual_rent_row["month"]       if annual_rent_row else None
    rent_provision = round(annual_rent / 12, 2) if annual_rent else None
    if rent_provision:
        spend["rent"] = round(spend.get("rent", 0.0) + rent_provision, 2)
        # Auto-populate rent budget from provision if user hasn't set one explicitly
        if "rent" not in budgets:
            budgets["rent"] = rent_provision

    # Car loan payment added automatically to 'car' category spend
    if car_loan_payment:
        spend["car"] = round(spend.get("car", 0.0) + car_loan_payment, 2)

    # Manual savings amount overrides transaction-based spend for the 'savings' category
    savings_actual = cfg.get("savings_actual")
    if savings_actual is not None:
        spend["savings"] = savings_actual

    all_cats = sorted(set(budgets) | set(spend) | {"savings", "family_support"})
    result: List[Dict[str, Any]] = []
    for cat in all_cats:
        budget    = budgets.get(cat)
        actual    = spend.get(cat, 0.0)
        remaining = round(budget - actual, 2) if budget is not None else None
        pct_used  = round(actual / budget * 100, 1) if budget else None
        result.append({
            "category":     cat,
            "budget_aed":   budget,
            "spent_aed":    actual,
            "remaining_aed": remaining,
            "pct_used":     pct_used,
            "manual_spend":    cat == "savings",
            "invert_surplus":  cat == "savings",  # over-budget is good for savings
        })

    income          = cfg.get("income")
    wife_income     = cfg.get("wife_income")
    savings_balance = cfg.get("savings_balance")
    total_income    = round((income or 0.0) + (wife_income or 0.0), 2) if (income is not None or wife_income is not None) else None
    total_spent     = round(sum(r["spent_aed"] for r in result), 2)
    # Net excludes savings: savings is a transfer to your own account, not an expense.
    # Net = income − expenses only; saving more than budgeted doesn't create a deficit.
    total_expenses  = round(sum(r["spent_aed"] for r in result if not r["invert_surplus"]), 2)
    net             = round(total_income - total_expenses, 2) if total_income is not None else None

    return {
        "year":               y,
        "month":              m,
        "income_aed":         income,
        "wife_income_aed":    wife_income,
        "total_income_aed":   total_income,
        "annual_rent_aed":    annual_rent,
        "annual_rent_year":   rent_year,
        "annual_rent_month":  rent_month,
        "rent_provision_aed": rent_provision,
        "savings_balance_aed": savings_balance,
        "total_spent_aed":    total_spent,
        "total_expenses_aed": total_expenses,
        "net_aed":            net,
        "categories":         result,
    }


# ---------------------------------------------------------------------------
# Monthly config endpoints
# ---------------------------------------------------------------------------

class MonthlyConfigIn(BaseModel):
    year:       str   = Field(..., pattern=r"^\d{4}$")
    month:      str   = Field(..., pattern=r"^(0[1-9]|1[0-2])$")
    key:        str   = Field(..., description="'income', 'savings_actual', or 'savings_balance'")
    amount_aed: float = Field(..., gt=0)


@router.post("/api/monthly-config", status_code=200)
def api_monthly_config_set(body: MonthlyConfigIn):
    """Set income, savings_actual, or savings_balance for a specific month."""
    if body.key not in _ALLOWED_CONFIG_KEYS:
        raise HTTPException(status_code=422, detail=f"key must be one of {_ALLOWED_CONFIG_KEYS}")
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO monthly_config (year, month, key, amount_aed) VALUES (?,?,?,?) "
            "ON CONFLICT(year, month, key) DO UPDATE SET amount_aed=excluded.amount_aed",
            (body.year, body.month, body.key, body.amount_aed),
        )
        con.commit()
    return {"year": body.year, "month": body.month, "key": body.key, "amount_aed": body.amount_aed}


@router.get("/api/monthly-config")
def api_monthly_config_list():
    """Retrieve all monthly config entries."""
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT year, month, key, amount_aed FROM monthly_config ORDER BY year, month, key").fetchall()
    return {"entries": [dict(r) for r in rows]}


@router.get("/api/budget-utilization")
def api_budget_utilization(
    year:  Optional[str] = Query(None),
    month: Optional[str] = Query(None),
):
    """
    Budget health for the selected month — three slices: on-track spend,
    overspent amount, and remaining budget. Only budgeted categories included.
    Car loan payment is injected automatically (same logic as /api/budget).
    """
    today = datetime.today()
    y = year or f"{today.year:04d}"
    m = (month or f"{today.month:02d}").zfill(2)
    ym_prefix = f"{y}-{m}%"

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row

        budgets: Dict[str, float] = {
            r["category"]: r["monthly_aed"]
            for r in con.execute("SELECT category, monthly_aed FROM budgets").fetchall()
        }

        spend_rows = con.execute(
            """
            SELECT category, ROUND(SUM(amount_aed), 2) AS spent
            FROM transactions
            WHERE amount_aed > 0
              AND txn_date LIKE ?
            GROUP BY category
            """,
            (ym_prefix,),
        ).fetchall()

        cfg_rows = con.execute(
            "SELECT key, amount_aed FROM monthly_config WHERE year=? AND month=?",
            (y, m),
        ).fetchall()

        annual_rent_row = con.execute(
            """
            SELECT year, month, amount_aed FROM monthly_config
            WHERE key = 'annual_rent' AND year || month <= ? || ?
            ORDER BY year DESC, month DESC LIMIT 1
            """,
            (y, m),
        ).fetchone()

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
            car_loan_payment = float(loan_row["next_payment_amount"] or 0.0)
        else:
            latest_loan = con.execute(
                """
                SELECT next_payment_amount, contract_signing_date, maturity_date
                FROM loan_statements ORDER BY statement_date DESC LIMIT 1
                """
            ).fetchone()
            if latest_loan and latest_loan["next_payment_amount"]:
                month_start = f"{y}-{m}-01"
                if latest_loan["contract_signing_date"] < month_start <= latest_loan["maturity_date"]:
                    car_loan_payment = float(latest_loan["next_payment_amount"])
                else:
                    car_loan_payment = 0.0
            else:
                car_loan_payment = 0.0

    spend = {r["category"]: r["spent"] for r in spend_rows}
    cfg   = {r["key"]: r["amount_aed"] for r in cfg_rows}

    annual_rent = annual_rent_row["amount_aed"] if annual_rent_row else None
    rent_provision = round(annual_rent / 12, 2) if annual_rent else None
    if rent_provision:
        spend["rent"] = round(spend.get("rent", 0.0) + rent_provision, 2)
        if "rent" not in budgets:
            budgets["rent"] = rent_provision

    if car_loan_payment:
        spend["car"] = round(spend.get("car", 0.0) + car_loan_payment, 2)

    savings_actual = cfg.get("savings_actual")
    if savings_actual is not None:
        spend["savings"] = savings_actual

    on_track  = 0.0
    overspent = 0.0
    remaining = 0.0

    for cat, budget in budgets.items():
        spent = spend.get(cat, 0.0)
        if spent >= budget:
            on_track  += budget
            overspent += spent - budget
        else:
            on_track  += spent
            remaining += budget - spent

    on_track     = round(on_track,  2)
    overspent    = round(overspent, 2)
    remaining    = round(remaining, 2)
    total_budget = round(sum(budgets.values()), 2)
    pct_used     = round((on_track + overspent) / total_budget * 100, 1) if total_budget else None

    # Per-category rows for bar chart visualization
    categories = []
    for cat, budget in budgets.items():
        spent    = spend.get(cat, 0.0)
        over     = round(max(spent - budget, 0.0), 2)
        within   = round(min(spent, budget), 2)
        rem      = round(max(budget - spent, 0.0), 2)
        pct      = round(spent / budget * 100, 1) if budget else None
        categories.append({
            "category": cat,
            "budget":   round(budget, 2),
            "spent":    round(spent,  2),
            "within":   within,
            "over":     over,
            "remaining": rem,
            "pct_used": pct,
        })
    categories.sort(key=lambda x: x["spent"], reverse=True)

    return {
        "slices": [
            {"label": "Spent (on track)", "value": on_track},
            {"label": "Overspent",        "value": overspent},
            {"label": "Remaining",        "value": remaining},
        ],
        "summary": [{
            "pct_used":     pct_used,
            "total_budget": total_budget,
            "remaining":    remaining,
            "overspent":    overspent,
        }],
        "categories":   categories,
        "total_budget": total_budget,
        "pct_used":     pct_used,
    }


@router.delete("/api/monthly-config/{year}/{month}/{key}", status_code=200)
def api_monthly_config_delete(year: str, month: str, key: str):
    """Remove a specific config key for a month."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "DELETE FROM monthly_config WHERE year=? AND month=? AND key=?",
            (year, month, key),
        )
        con.commit()
    return {"deleted": {"year": year, "month": month, "key": key}}
