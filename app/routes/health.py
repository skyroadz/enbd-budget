"""
Routes: GET /health, GET /metrics
"""
import sqlite3
import time

from fastapi import APIRouter, Response
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST

from ..config import DB_PATH, CHEQUING_DIR, SAVINGS_DIR, LOANS_DIR
from ..rules import load_rules
from ..ingestion import ingest_incremental, compute_category_aggregates, compute_merchant_aggregates_all

router = APIRouter()


@router.get("/health")
def health():
    """Liveness check — confirms the app is running and the DB is reachable."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("SELECT 1")
    return {"status": "ok"}


@router.get("/metrics")
def metrics():
    """
    Prometheus metrics endpoint. Also triggers incremental ingestion of any
    new/changed PDFs in all statement directories.
    """
    # Reload rules first (triggers auto-recategorize if rules.yaml changed)
    load_rules()

    try:
        files_ingested = ingest_incremental()
    except sqlite3.OperationalError:
        files_ingested = 0

    try:
        from parsers.bank_parsers import ingest_chequing_dir, ingest_savings_dir
        ingest_chequing_dir(CHEQUING_DIR, DB_PATH)
        ingest_savings_dir(SAVINGS_DIR, DB_PATH)
    except sqlite3.OperationalError:
        pass

    try:
        from parsers.loan_parser import ingest_loans_dir
        ingest_loans_dir(LOANS_DIR, DB_PATH)
    except sqlite3.OperationalError:
        pass

    cat_agg   = compute_category_aggregates()
    merch_agg = compute_merchant_aggregates_all()

    reg = CollectorRegistry()

    g_total = Gauge(
        "spend_aed_total",
        "Total spend in AED (credits negative)",
        ["ym", "year", "month", "category", "card_scope"],
        registry=reg,
    )
    g_count = Gauge(
        "spend_aed_txn_count",
        "Transaction count",
        ["ym", "year", "month", "category", "card_scope"],
        registry=reg,
    )
    g_refunds = Gauge(
        "spend_aed_refunds_total",
        "Refunds total (absolute AED)",
        ["ym", "year", "month", "category", "card_scope"],
        registry=reg,
    )
    g_debit_count = Gauge(
        "spend_aed_debit_txn_count",
        "Debit-only transaction count (excludes refunds/credits)",
        ["ym", "year", "month", "category", "card_scope"],
        registry=reg,
    )
    g_merch_total = Gauge(
        "spend_aed_total_by_merchant",
        "Total spend in AED by merchant (includes category label)",
        ["ym", "year", "month", "category", "merchant", "card_scope"],
        registry=reg,
    )
    g_last     = Gauge("spend_last_processed_unixtime",    "Last processed unix timestamp",             registry=reg)
    g_ingested = Gauge("spend_files_ingested_last_scrape", "Number of PDFs ingested on last scrape",    registry=reg)

    for (year, month, category, card_scope), v in cat_agg.items():
        ym = f"{year}-{month}"
        g_total.labels(ym=ym,        year=year, month=month, category=category, card_scope=card_scope).set(v["total"])
        g_count.labels(ym=ym,        year=year, month=month, category=category, card_scope=card_scope).set(v["count"])
        g_refunds.labels(ym=ym,      year=year, month=month, category=category, card_scope=card_scope).set(v["refunds"])
        g_debit_count.labels(ym=ym,  year=year, month=month, category=category, card_scope=card_scope).set(v["debit_count"])

    for (year, month, category, merchant, card_scope), total in merch_agg.items():
        ym = f"{year}-{month}"
        g_merch_total.labels(ym=ym, year=year, month=month, category=category, merchant=merchant, card_scope=card_scope).set(total)

    g_last.set(time.time())
    g_ingested.set(float(files_ingested))

    return Response(generate_latest(reg), media_type=CONTENT_TYPE_LATEST)
