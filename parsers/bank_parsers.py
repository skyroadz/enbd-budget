"""
Parsers for Emirates NBD chequing and savings account PDF statements.

Two statement formats are supported:

NEW format (2025+ "STATEMENT OF ACCOUNT"):
  - Period line: "FOR THE PERIOD OF 01 Jan 2025 to 31 Jan 2025"
  - Transaction date: "DD Mon YYYY"
  - Balance column: "NNN.NN Cr" (space before Cr) at end of FIRST transaction line
  - Transactions in reverse chronological order

OLD format (2024 E-STATEMENT, password-protected PDFs):
  - Period line: "From DD/MM/YYYY to DD/MM/YYYY" (pdfplumber may add spaces in date)
  - Transaction date: "DDMMMYY" e.g. "04JUL24"
  - Balance column: "NNN.NNCr" (no space) on the LAST line of each block
  - Credit/debit determined by comparing balance change to transaction amount
"""
import hashlib
import logging
import re
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pdfplumber

log = logging.getLogger(__name__)

MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

# ---------------------------------------------------------------------------
# NEW format regexes (2025+ "STATEMENT OF ACCOUNT")
# ---------------------------------------------------------------------------
# "STATEMENT OF ACCOUNT FOR THE PERIOD OF 01 Jan 2025 to 31 Jan 2025"
PERIOD_RE   = re.compile(r"FOR THE PERIOD OF \d{2} \w+ \d{4} to \d{2} (\w{3}) (\d{4})")
IBAN_RE     = re.compile(r"\bIBAN\s+(AE\w+)")
ACCT_RE     = re.compile(r"Account Type\s+(.+)")
TXN_DATE_RE = re.compile(r"^(\d{2} \w{3} \d{4})\s+")
BALANCE_RE  = re.compile(r"\s+([\d,]+\.\d{2})\s+Cr$")
AMOUNT_RE   = re.compile(r"\s+(-?[\d,]+(?:\.\d+)?)$")
PAGE_END_RE = re.compile(r"^\d+ / \d+$")

# ---------------------------------------------------------------------------
# OLD format regexes (2024 E-STATEMENT)
# ---------------------------------------------------------------------------
# "From 0 2/07/ 2024 to ..." — pdfplumber may insert spaces inside the date digits
# Capture start-date month (group 1) and year (group 2) to identify the statement month
OLD_PERIOD_RE    = re.compile(r"From\s+[\d\s]*/\s*(\d{2})\s*/\s*(\d{4})")
OLD_TXN_DATE_RE  = re.compile(r"^(\d{2}[A-Z]{3}\d{2})\s+")
OLD_BALANCE_RE   = re.compile(r"([\d,]+\.\d{2})Cr$")            # "96,023.41Cr"
OLD_LAST_LINE_RE = re.compile(r"\s*([\d,]+\.\d{2})\s+([\d,]+\.\d{2})Cr$")  # "amount balanceCr"


def _to_float(s: str) -> float:
    return float(s.replace(',', ''))


def _extract_lines(pdf_path: Path) -> List[str]:
    lines = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for ln in (page.extract_text() or "").splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(ln)
    return lines


def _parse_txn_block(block: List[str]) -> Optional[Dict]:
    """Parse a multi-line transaction block (first line has date+amounts)."""
    if not block:
        return None
    first = block[0]
    date_m = TXN_DATE_RE.match(first)
    if not date_m:
        return None

    rest = first[date_m.end():]

    bal_m = BALANCE_RE.search(rest)
    if not bal_m:
        return None
    balance = _to_float(bal_m.group(1))
    before_bal = rest[:bal_m.start()]

    amt_m = AMOUNT_RE.search(before_bal)
    if not amt_m:
        return None
    amount = _to_float(amt_m.group(1))
    desc_part = before_bal[:amt_m.start()].strip()

    # Continuation lines are description-only (no amounts)
    continuation = " ".join(block[1:]).strip()
    full_desc = (desc_part + " " + continuation).strip()

    return {
        "date":      date_m.group(1),
        "desc":      full_desc,
        "amount":    abs(amount),
        "is_credit": amount > 0,
        "balance":   balance,
    }


def _parse_new_format(lines: List[str]) -> Dict:
    """Parse 2025+ 'STATEMENT OF ACCOUNT FOR THE PERIOD OF' format."""
    iban = account_type = year = month = None
    for ln in lines:
        if m := IBAN_RE.search(ln):
            iban = m.group(1)
        if m := ACCT_RE.search(ln):
            account_type = m.group(1).strip()
        if m := PERIOD_RE.search(ln):
            month = MONTH_MAP.get(m.group(1), '01')
            year  = m.group(2)

    transactions: List[Dict] = []
    in_table = False
    current_block: List[str] = []

    for ln in lines:
        if ("Date Description" in ln or "Date Details" in ln) and "Balance" in ln:
            in_table = True
            continue
        if not in_table:
            continue
        if ln.startswith("This is an electronically") or PAGE_END_RE.match(ln):
            if current_block:
                txn = _parse_txn_block(current_block)
                if txn:
                    transactions.append(txn)
                current_block = []
            continue
        if TXN_DATE_RE.match(ln):
            if current_block:
                txn = _parse_txn_block(current_block)
                if txn:
                    transactions.append(txn)
            current_block = [ln]
        else:
            current_block.append(ln)

    if current_block:
        txn = _parse_txn_block(current_block)
        if txn:
            transactions.append(txn)

    return {
        "iban":         iban,
        "account_type": account_type,
        "year":         year,
        "month":        month,
        "transactions": transactions,
    }


# ---------------------------------------------------------------------------
# OLD format helpers
# ---------------------------------------------------------------------------

def _parse_old_txn_block(block: List[str]) -> Optional[Dict]:
    """
    Parse old-format transaction block where amounts are on the LAST line.

    block[0]:    'DDMMMYY description_start...'
    block[1..n]: description continuation
    block[-1]:   '...description_end  amount  balanceCr'

    Returns dict with raw date_str (not yet ISO), desc, amount, balance.
    is_credit is resolved by the caller from balance changes.
    """
    if not block:
        return None
    first  = block[0]
    date_m = OLD_TXN_DATE_RE.match(first)
    if not date_m:
        return None

    last   = block[-1]
    last_m = OLD_LAST_LINE_RE.search(last)
    if not last_m:
        return None

    amount  = _to_float(last_m.group(1))
    balance = _to_float(last_m.group(2))

    if len(block) == 1:
        full_desc = first[date_m.end():last_m.start()].strip()
    else:
        first_desc  = first[date_m.end():].strip()
        middle_desc = " ".join(block[1:-1]).strip()
        last_desc   = last[:last_m.start()].strip()
        full_desc   = " ".join(filter(None, [first_desc, middle_desc, last_desc])).strip()

    return {
        "date_str": date_m.group(1),
        "desc":     full_desc,
        "amount":   amount,
        "balance":  balance,
    }


def _parse_old_format(lines: List[str]) -> Dict:
    """Parse 2024 E-STATEMENT format with DDMMMYY dates and balanceCr line endings."""
    year = month = account_type = None

    for ln in lines:
        if m := OLD_PERIOD_RE.search(ln):
            month = m.group(1)   # start-date month identifies the statement
            year  = m.group(2)
        if m := re.search(r"Account type\s+(.+)", ln, re.IGNORECASE):
            account_type = m.group(1).strip()

    raw_txns: List[Dict]     = []
    in_table                 = False
    current_block: List[str] = []
    initial_balance          = 0.0
    got_initial_balance      = False

    for ln in lines:
        if ("Date Description" in ln or "Date Details" in ln) and "Balance" in ln:
            in_table = True
            continue
        if not in_table:
            continue

        if OLD_TXN_DATE_RE.match(ln):
            # Flush previous block
            if current_block:
                t = _parse_old_txn_block(current_block)
                if t:
                    raw_txns.append(t)
                current_block = []

            if "BROUGHT FORWARD" in ln:
                if not got_initial_balance:
                    bal_m = OLD_BALANCE_RE.search(ln)
                    initial_balance = _to_float(bal_m.group(1)) if bal_m else 0.0
                    got_initial_balance = True
                continue   # not a real transaction

            current_block = [ln]

        elif "CARRIED FORWARD" in ln:
            if current_block:
                t = _parse_old_txn_block(current_block)
                if t:
                    raw_txns.append(t)
                current_block = []

        else:
            # Continuation line; skip page-number headers even mid-block
            if current_block and not re.match(r"^Page \d+ of \d+$", ln):
                current_block.append(ln)

    if current_block:
        t = _parse_old_txn_block(current_block)
        if t:
            raw_txns.append(t)

    # Resolve is_credit from balance changes:
    #   Credit → new_balance = prev + amount → diff ≈ +amount
    #   Debit  → new_balance = prev - amount → diff ≈ -amount
    transactions: List[Dict] = []
    prev_bal = initial_balance
    for rt in raw_txns:
        diff      = rt["balance"] - prev_bal
        is_credit = abs(diff - rt["amount"]) < 0.01
        transactions.append({
            "date":      rt["date_str"],
            "desc":      rt["desc"],
            "amount":    rt["amount"],
            "is_credit": is_credit,
            "balance":   rt["balance"],
        })
        prev_bal = rt["balance"]

    return {
        "iban":         None,   # masked in old format
        "account_type": account_type,
        "year":         year,
        "month":        month,
        "transactions": transactions,
    }


def parse_enbd_statement(pdf_path: Path) -> Dict:
    """
    Parse any Emirates NBD account statement PDF (new or old format).
    Returns: {iban, account_type, year, month, transactions}
    """
    lines = _extract_lines(pdf_path)
    if any("FOR THE PERIOD OF" in ln for ln in lines):
        return _parse_new_format(lines)
    return _parse_old_format(lines)


# ---------------------------------------------------------------------------
# Chequing: extract income (salary credits)
# ---------------------------------------------------------------------------

def extract_chequing_data(pdf_path: Path) -> Optional[Dict]:
    """
    Parse a chequing statement and extract:
      - income: sum of credit transactions containing 'Salary'
    Returns None if period could not be determined.
    """
    stmt = parse_enbd_statement(pdf_path)
    if not stmt["year"]:
        log.warning("bank_parsers: could not read period from %s", pdf_path.name)
        return None

    income = sum(
        t["amount"]
        for t in stmt["transactions"]
        if "SALARY" in t["desc"].upper()
    )

    log.info(
        "bank_parsers: chequing %s/%s — income=%.2f",
        stmt["year"], stmt["month"], income,
    )
    return {
        "year":   stmt["year"],
        "month":  stmt["month"],
        "income": round(income, 2),
        "iban":   stmt["iban"],
    }


# ---------------------------------------------------------------------------
# Savings: extract closing balance + transfers in
# ---------------------------------------------------------------------------

def extract_savings_data(pdf_path: Path) -> Optional[Dict]:
    """
    Parse a savings statement and extract:
      - closing_balance: balance after the most recent transaction
      - savings_received: sum of 'MOBILE BANKING TRANSFER FROM' credits
        (transfers in from chequing account)
    Returns None if period could not be determined.
    """
    stmt = parse_enbd_statement(pdf_path)
    if not stmt["year"]:
        log.warning("bank_parsers: could not read period from %s", pdf_path.name)
        return None

    txns = stmt["transactions"]
    closing_balance = txns[0]["balance"] if txns else 0.0

    savings_received = sum(
        t["amount"]
        for t in txns
        if t["is_credit"] and "MOBILE BANKING TRANSFER FROM" in t["desc"].upper()
    )

    log.info(
        "bank_parsers: savings %s/%s — balance=%.2f received=%.2f",
        stmt["year"], stmt["month"], closing_balance, savings_received,
    )
    return {
        "year":             stmt["year"],
        "month":            stmt["month"],
        "closing_balance":  round(closing_balance, 2),
        "savings_received": round(savings_received, 2),
        "iban":             stmt["iban"],
    }


# ---------------------------------------------------------------------------
# Incremental ingestion helpers (called from app.py)
# ---------------------------------------------------------------------------

def _bank_file_key(folder: str, pdf_path: Path) -> str:
    """Unique key for ingested_files — prefixed to avoid clashes with CC statements."""
    return f"{folder}/{pdf_path.name}"


def _should_ingest_bank(con: sqlite3.Connection, key: str, pdf_path: Path) -> bool:
    st = pdf_path.stat()
    mtime, size = int(st.st_mtime), int(st.st_size)
    row = con.execute(
        "SELECT mtime, size FROM ingested_files WHERE statement_file = ?", (key,)
    ).fetchone()
    if row is None:
        return True
    return int(row[0]) != mtime or int(row[1]) != size


def _mark_ingested_bank(con: sqlite3.Connection, key: str, pdf_path: Path):
    st = pdf_path.stat()
    con.execute("""
        INSERT INTO ingested_files(statement_file, mtime, size, last_ingested_unixtime)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(statement_file) DO UPDATE SET
          mtime=excluded.mtime, size=excluded.size,
          last_ingested_unixtime=excluded.last_ingested_unixtime
    """, (key, int(st.st_mtime), int(st.st_size), int(time.time())))


def _upsert_config(con: sqlite3.Connection, year: str, month: str, key: str, amount: float):
    con.execute("""
        INSERT INTO monthly_config (year, month, key, amount_aed) VALUES (?,?,?,?)
        ON CONFLICT(year, month, key) DO UPDATE SET amount_aed=excluded.amount_aed
    """, (year, month, key, amount))


def _parse_txn_date(date_str: str) -> str:
    """Convert 'DD Mon YYYY' (new format) or 'DDMMMYY' (old format) → 'YYYY-MM-DD'."""
    try:
        return datetime.strptime(date_str, "%d %b %Y").strftime("%Y-%m-%d")
    except ValueError:
        # Old format: 'DDMMMYY' e.g. '04JUL24'
        day = date_str[:2]
        mon = date_str[2:5].capitalize()   # 'JUL' → 'Jul'
        yr  = '20' + date_str[5:7]
        return datetime.strptime(f"{day} {mon} {yr}", "%d %b %Y").strftime("%Y-%m-%d")


def _txn_id(account: str, date_iso: str, desc: str, amount: float, is_credit: bool) -> str:
    base = f"{account}|{date_iso}|{desc}|{amount}|{is_credit}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _store_bank_transactions(
    con: sqlite3.Connection,
    account: str,
    transactions: List[Dict],
    statement_file: str,
):
    """Upsert all transactions from a parsed statement into bank_transactions."""
    for t in transactions:
        try:
            date_iso = _parse_txn_date(t["date"])
        except ValueError:
            continue
        tid = _txn_id(account, date_iso, t["desc"], t["amount"], t["is_credit"])
        con.execute("""
            INSERT INTO bank_transactions
                (id, account, txn_date, description, amount, is_credit, balance, statement_file)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                description=excluded.description,
                balance=excluded.balance,
                statement_file=excluded.statement_file
        """, (tid, account, date_iso, t["desc"], t["amount"],
              int(t["is_credit"]), t["balance"], statement_file))


def ingest_chequing_dir(chequing_dir: Path, db_path: Path) -> int:
    """
    Scan chequing_dir for new/changed PDFs, parse each one, write
    income into monthly_config and all transactions into bank_transactions.
    Returns number of files processed.
    """
    chequing_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(chequing_dir.glob("*.pdf"))
    processed = 0
    with sqlite3.connect(db_path, timeout=30) as con:
        con.execute("PRAGMA busy_timeout=10000")
        for pdf in pdfs:
            key = _bank_file_key("chequing", pdf)
            if not _should_ingest_bank(con, key, pdf):
                continue
            try:
                stmt = parse_enbd_statement(pdf)
                if not stmt["year"]:
                    continue
                # Store transactions
                _store_bank_transactions(con, "chequing", stmt["transactions"], pdf.name)
                # Write income aggregate
                income = sum(
                    t["amount"] for t in stmt["transactions"]
                    if "SALARY" in t["desc"].upper()
                )
                if income > 0:
                    _upsert_config(con, stmt["year"], stmt["month"], "income", round(income, 2))
                _mark_ingested_bank(con, key, pdf)
                con.commit()
                processed += 1
                log.info("bank_parsers: chequing %s/%s — %d txns, income=%.2f",
                         stmt["year"], stmt["month"], len(stmt["transactions"]), income)
            except Exception as e:
                log.error("bank_parsers: error parsing chequing %s: %s", pdf.name, e)
    return processed


def ingest_savings_dir(savings_dir: Path, db_path: Path) -> int:
    """
    Scan savings_dir for new/changed PDFs, parse each one, write
    savings_balance + savings_actual into monthly_config and all
    transactions into bank_transactions. Returns number of files processed.
    """
    savings_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(savings_dir.glob("*.pdf"))
    processed = 0
    with sqlite3.connect(db_path, timeout=30) as con:
        con.execute("PRAGMA busy_timeout=10000")
        for pdf in pdfs:
            key = _bank_file_key("savings", pdf)
            if not _should_ingest_bank(con, key, pdf):
                continue
            try:
                stmt = parse_enbd_statement(pdf)
                if not stmt["year"]:
                    continue
                txns = stmt["transactions"]
                # Store transactions
                _store_bank_transactions(con, "savings", txns, pdf.name)
                # Write aggregates
                closing_balance = txns[0]["balance"] if txns else 0.0
                savings_received = sum(
                    t["amount"] for t in txns
                    if t["is_credit"] and "MOBILE BANKING TRANSFER FROM" in t["desc"].upper()
                )
                _upsert_config(con, stmt["year"], stmt["month"], "savings_balance", round(closing_balance, 2))
                if savings_received > 0:
                    _upsert_config(con, stmt["year"], stmt["month"], "savings_actual", round(savings_received, 2))
                _mark_ingested_bank(con, key, pdf)
                con.commit()
                processed += 1
                log.info("bank_parsers: savings %s/%s — %d txns, balance=%.2f received=%.2f",
                         stmt["year"], stmt["month"], len(txns), closing_balance, savings_received)
            except Exception as e:
                log.error("bank_parsers: error parsing savings %s: %s", pdf.name, e)
    return processed
