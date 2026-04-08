"""
Database layer: schema initialisation, stable IDs, upsert helpers, file-tracking.
"""
import hashlib
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config import DB_PATH

log = logging.getLogger(__name__)


def init_db() -> None:
    """
    Create tables if missing and perform simple schema migrations for older DB versions.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            txn_date TEXT,
            post_date TEXT,
            description_raw TEXT,
            amount_aed REAL,
            is_credit INTEGER,
            card_scope TEXT,
            orig_currency TEXT,
            orig_amount REAL,
            statement_file TEXT
        )
        """)

        # Migrate: ensure new columns exist
        existing_cols = {row[1] for row in con.execute("PRAGMA table_info(transactions)").fetchall()}
        if "merchant" not in existing_cols:
            con.execute("ALTER TABLE transactions ADD COLUMN merchant TEXT")
        if "category" not in existing_cols:
            con.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
        if "category_locked" not in existing_cols:
            con.execute("ALTER TABLE transactions ADD COLUMN category_locked INTEGER NOT NULL DEFAULT 0")
        if "ml_confidence" not in existing_cols:
            con.execute("ALTER TABLE transactions ADD COLUMN ml_confidence REAL")

        con.execute("""
        CREATE TABLE IF NOT EXISTS ingested_files (
            statement_file TEXT PRIMARY KEY,
            mtime INTEGER NOT NULL,
            size INTEGER NOT NULL,
            last_ingested_unixtime INTEGER NOT NULL
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            category TEXT PRIMARY KEY,
            monthly_aed REAL NOT NULL
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS monthly_config (
            year  TEXT NOT NULL,
            month TEXT NOT NULL,
            key   TEXT NOT NULL,
            amount_aed REAL NOT NULL,
            PRIMARY KEY (year, month, key)
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS bank_transactions (
            id           TEXT PRIMARY KEY,
            account      TEXT NOT NULL,
            txn_date     TEXT NOT NULL,
            description  TEXT NOT NULL,
            amount       REAL NOT NULL,
            is_credit    INTEGER NOT NULL,
            balance      REAL NOT NULL,
            statement_file TEXT NOT NULL
        )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_bank_txn_account ON bank_transactions(account)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_bank_txn_date    ON bank_transactions(txn_date)")

        con.execute("""
        CREATE TABLE IF NOT EXISTS loan_statements (
            id                      TEXT PRIMARY KEY,
            statement_file          TEXT,
            account_no              TEXT,
            statement_date          TEXT,
            contract_signing_date   TEXT,
            maturity_date           TEXT,
            finance_amount          REAL,
            total_profit_amount     REAL,
            outstanding_principal   REAL,
            remaining_profit        REAL,
            total_outstanding       REAL,
            next_payment_amount     REAL,
            next_payment_date       TEXT,
            remaining_installments  INTEGER,
            last_ingested_unixtime  INTEGER
        )
        """)

        con.execute("CREATE INDEX IF NOT EXISTS idx_txn_date     ON transactions(txn_date)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_txn_merchant ON transactions(merchant)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions(category)")
        con.commit()


def stable_txn_id(txn_date: str, post_date: str, desc: str, amount_aed: float, card_scope: str) -> str:
    """
    Deterministic ID for de-duplication. Uses sha256 (truncated to 16 hex chars) so it is
    stable across process restarts (Python's built-in hash() is salted per-process).
    """
    base = f"{txn_date}|{post_date}|{desc}|{amount_aed}|{card_scope}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def year_month_of(date_iso: str) -> Tuple[str, str]:
    """'YYYY-MM-DD' → ('YYYY', 'MM')"""
    return date_iso[0:4], date_iso[5:7]


def file_sig(p: Path) -> Tuple[int, int]:
    st = p.stat()
    return int(st.st_mtime), int(st.st_size)


def should_ingest(con: sqlite3.Connection, pdf_path: Path) -> bool:
    mtime, size = file_sig(pdf_path)
    row = con.execute(
        "SELECT mtime, size FROM ingested_files WHERE statement_file = ?",
        (pdf_path.name,),
    ).fetchone()
    if row is None:
        return True
    return (int(row[0]) != mtime) or (int(row[1]) != size)


def mark_ingested(con: sqlite3.Connection, pdf_path: Path) -> None:
    mtime, size = file_sig(pdf_path)
    con.execute("""
    INSERT INTO ingested_files(statement_file, mtime, size, last_ingested_unixtime)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(statement_file) DO UPDATE SET
      mtime=excluded.mtime,
      size=excluded.size,
      last_ingested_unixtime=excluded.last_ingested_unixtime
    """, (pdf_path.name, mtime, size, int(time.time())))


def upsert_rows(con: sqlite3.Connection, rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Insert rows into the DB. Returns (inserted, skipped) counts.
    """
    inserted = 0
    skipped = 0
    for r in rows:
        rid = stable_txn_id(
            r["txn_date"], r["post_date"], r["description_raw"], r["amount_aed"], r["card_scope"],
        )
        cur = con.execute("""
        INSERT OR IGNORE INTO transactions
        (id, txn_date, post_date, description_raw, merchant, category, ml_confidence,
         amount_aed, is_credit, card_scope, orig_currency, orig_amount, statement_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rid,
            r["txn_date"], r["post_date"], r["description_raw"],
            r["merchant"], r["category"], r.get("ml_confidence"),
            r["amount_aed"], r["is_credit"],
            r["card_scope"], r["orig_currency"], r["orig_amount"], r["statement_file"],
        ))
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1
            log.debug("Skipped duplicate txn id=%s desc=%r", rid, r["description_raw"])
    return inserted, skipped
