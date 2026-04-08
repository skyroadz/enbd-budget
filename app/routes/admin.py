"""
Routes: POST /admin/recategorize, GET /admin/uncategorized, POST /admin/ingest-bank,
        POST /admin/retrain
"""
import logging
import os
import sqlite3
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException

from ..config import DB_PATH, CHEQUING_DIR, SAVINGS_DIR
from ..rules import recategorize_db, audit_rules

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("/admin/recategorize")
def admin_recategorize():
    """Force re-categorisation of all transactions using the current rules.yaml."""
    n = recategorize_db()
    log.info("Recategorization complete: %d rows updated", n)
    return {"updated_rows": n}


@router.post("/admin/unlock-uncategorized")
def admin_unlock_uncategorized():
    """Unlock transactions that are locked but still uncategorized (stuck rows).
    Safe to run — only affects rows with no useful category set."""
    with sqlite3.connect(DB_PATH) as con:
        n = con.execute(
            "UPDATE transactions SET category_locked=0 WHERE category='uncategorized' AND category_locked=1"
        ).rowcount
        con.commit()
    return {"unlocked_rows": n}


@router.get("/admin/uncategorized")
def admin_uncategorized():
    """Return uncategorized merchants with the ML model's best prediction for each."""
    from .. import ml_model
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT merchant, COUNT(*) AS txn_count, ROUND(SUM(amount_aed), 2) AS total_aed
            FROM transactions
            WHERE category = 'uncategorized'
            GROUP BY merchant
            ORDER BY COUNT(*) DESC
        """).fetchall()

    result = []
    for r in rows:
        ml_cat, ml_conf = ml_model.predict(r["merchant"])
        result.append({
            "merchant":                 r["merchant"],
            "txn_count":                r["txn_count"],
            "total_aed":                r["total_aed"],
            "ml_prediction":            ml_cat,
            "ml_prediction_confidence": round(ml_conf, 3) if ml_conf else None,
        })
    return {"uncategorized_merchants": result}


@router.post("/admin/categorize-merchant")
def admin_categorize_merchant(body: dict):
    """Lock all transactions for a merchant to the given category."""
    merchant = body.get("merchant", "").strip()
    category = body.get("category", "").strip()
    if not merchant or not category:
        raise HTTPException(status_code=400, detail="merchant and category required")
    with sqlite3.connect(DB_PATH) as con:
        res = con.execute(
            "UPDATE transactions SET category=?, category_locked=1, ml_confidence=NULL "
            "WHERE merchant=?",
            (category, merchant),
        )
        con.commit()
    return {"updated": res.rowcount}


@router.get("/admin/audit-rules")
def admin_audit_rules():
    """Compare rules.yaml against manually-locked transactions to find wrong or missing rules."""
    return audit_rules()


@router.post("/admin/retrain")
def admin_retrain():
    """
    Trigger the ml-trainer container to retrain the categorisation model
    from the current state.db, then hot-reload it in this process.
    """
    trainer_url = os.getenv("ML_TRAINER_URL", "http://ml-trainer:8001")
    try:
        req = urllib.request.Request(
            f"{trainer_url}/retrain",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=b"",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            import json
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=exc.read().decode())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ml-trainer unreachable: {exc}")

    # Hot-reload the updated model in this process
    from .. import ml_model
    ml_model.reload()

    return result


@router.post("/admin/ingest-bank")
def admin_ingest_bank():
    """Re-scan chequing and savings directories and ingest any new/changed statements."""
    from parsers.bank_parsers import ingest_chequing_dir, ingest_savings_dir
    chequing_count = ingest_chequing_dir(CHEQUING_DIR, DB_PATH)
    savings_count  = ingest_savings_dir(SAVINGS_DIR, DB_PATH)
    return {"chequing_files_processed": chequing_count, "savings_files_processed": savings_count}
