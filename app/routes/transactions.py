"""
Routes: GET /transactions, PATCH /transactions/{id}/category, GET /api/bank-transactions
"""
import sqlite3
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import DB_PATH

router = APIRouter()


@router.get("/transactions")
def transactions(
    limit:    int            = Query(200, ge=1, le=5000),
    year:     Optional[str]  = Query(None, description="Filter by YYYY"),
    month:    Optional[str]  = Query(None, description="Filter by MM (01..12)"),
    merchant: Optional[str]  = Query(None, description="Filter by exact merchant name (case-insensitive)"),
    category: Optional[str]  = Query(None),
):
    """
    Credit card transactions. Both year and month can be used independently or together.
    """
    where: List[str] = []
    params: List[Any] = []

    if year and month:
        where.append("txn_date LIKE ?")
        params.append(f"{year}-{month}%")
    elif year:
        where.append("txn_date LIKE ?")
        params.append(f"{year}-%")
    elif month:
        where.append("strftime('%m', txn_date) = ?")
        params.append(month.zfill(2))

    if merchant:
        where.append("UPPER(merchant) = UPPER(?)")
        params.append(merchant)

    if category:
        where.append("category = ?")
        params.append(category)

    sql = """
      SELECT id, txn_date, post_date, merchant, category, category_locked,
             description_raw, amount_aed, card_scope, statement_file
      FROM transactions
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY txn_date DESC, post_date DESC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()

    return {"items": [dict(r) for r in rows]}


class CategoryOverride(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)


@router.patch("/transactions/{txn_id}/category", status_code=200)
def override_transaction_category(txn_id: str, body: CategoryOverride):
    """
    Manually override the category for a specific transaction.
    Sets category_locked=1 so auto-recategorization won't overwrite it.
    """
    with sqlite3.connect(DB_PATH) as con:
        try:
            res = con.execute(
                "UPDATE transactions SET category=?, category_locked=1 WHERE id=?",
                (body.category, txn_id),
            )
        except Exception:
            # category_locked column may not exist yet (server restart pending for migration)
            res = con.execute(
                "UPDATE transactions SET category=? WHERE id=?",
                (body.category, txn_id),
            )
        con.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"id": txn_id, "category": body.category, "category_locked": True}


@router.delete("/transactions/{txn_id}/category-override", status_code=200)
def clear_transaction_category_override(txn_id: str):
    """
    Remove a manual category override — transaction will be re-categorized by rules on next run.
    """
    with sqlite3.connect(DB_PATH) as con:
        # Re-derive category from current rules
        from ..rules import merchant_from_description, categorize, load_rules
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT description_raw FROM transactions WHERE id=?", (txn_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transaction not found")
        rules = load_rules()
        merchant = merchant_from_description(row["description_raw"], rules)
        category, ml_conf = categorize(merchant, row["description_raw"], rules)
        con.execute(
            "UPDATE transactions SET category=?, merchant=?, ml_confidence=?, category_locked=0 WHERE id=?",
            (category, merchant, ml_conf, txn_id),
        )
        con.commit()
    return {"id": txn_id, "category": category, "category_locked": False}


@router.get("/api/bank-transactions")
def api_bank_transactions(
    account: str           = Query(..., description="'chequing' or 'savings'"),
    year:    Optional[str] = Query(None, description="YYYY filter"),
    month:   Optional[str] = Query(None, description="MM filter"),
    limit:   int           = Query(500, ge=1, le=5000),
):
    """All transactions from bank statements for the given account, newest first."""
    where = ["account = ?"]
    params: List[Any] = [account]

    if year and month:
        where.append("txn_date LIKE ?")
        params.append(f"{year}-{month.zfill(2)}%")
    elif year:
        where.append("txn_date LIKE ?")
        params.append(f"{year}-%")
    elif month:
        where.append("strftime('%m', txn_date) = ?")
        params.append(month.zfill(2))

    params.append(limit)
    sql = f"""
        SELECT txn_date, description, amount, is_credit, balance
        FROM bank_transactions
        WHERE {" AND ".join(where)}
        ORDER BY txn_date DESC, rowid DESC
        LIMIT ?
    """
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()

    return {
        "account": account,
        "transactions": [
            {
                "txn_date":    r["txn_date"],
                "description": r["description"],
                "amount":      r["amount"],
                "is_credit":   bool(r["is_credit"]),
                "balance":     r["balance"],
            }
            for r in rows
        ],
    }
