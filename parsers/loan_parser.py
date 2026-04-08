"""
Parser for ADIB (Abu Dhabi Islamic Bank) finance/loan account statement PDFs.

Statement layout:
  Header (repeated on every page):
    Statement Date, Account No, Contract Signing Date, Maturity Date,
    Finance Amount, Total Profit Amount, Total Price Amount,
    Total outstanding cost amount (Principal), Total Remaining Profit Amount,
    Next Payment Amount, Next Payment Due Date, Remaining Number of Installments

  Transaction table:
    DD/MM/YYYY  Description  Debit  Credit  (Balance)

  Footer (last page of transactions):
    Total Outstanding Amount as of DD/MM/YYYY  (NNN.NN)
"""
import hashlib
import logging
import re
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Header regexes
# ---------------------------------------------------------------------------
STMT_DATE_RE     = re.compile(r"Statement Date\s*:\s*(\d{2}/\d{2}/\d{4})")
ACCOUNT_RE       = re.compile(r"Account No\.\s*:\s*(.+?)(?:\s{2,}|$)")
MATURITY_RE      = re.compile(r"Maturity Date\s*:\s*(\d{2}/\d{2}/\d{4})")
SIGNING_RE       = re.compile(r"Contract Signing Date\s*:\s*(\d{2}/\d{2}/\d{4})")
FINANCE_AMT_RE   = re.compile(r"Finance Amount\s*:\s*([\d,]+\.\d{2})")
TOTAL_PROFIT_RE  = re.compile(r"Total Profit Amount\s*:\s*([\d,]+\.\d{2})")
OUTSTANDING_PR_RE = re.compile(r"Total outstanding cost amount \(Principal\)\s*:\s*([\d,]+\.\d{2})")
REMAINING_PRF_RE = re.compile(r"Total Remaining Profit Amount\s*:\s*([\d,]+\.\d{2})")
TOTAL_OUTST_RE   = re.compile(r"Total Outstanding Amount as of \d{2}/\d{2}/\d{4}\s+\(([\d,]+\.\d{2})\)")
NEXT_PAY_RE      = re.compile(r"Next Payment Amount\s*:\s*([\d,]+\.\d{2})")
NEXT_DATE_RE     = re.compile(r"Next Payment Due Date\s*:\s*(\d{2}/\d{2}/\d{4})")
REMAINING_INST_RE = re.compile(r"Remaining Number of Installments\s*:\s*(\d+)")

# ---------------------------------------------------------------------------
# Transaction regexes
# ---------------------------------------------------------------------------
TXN_START_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+")
# Capture: debit (may be "(NNN.NN)" or "NNN.NN"), credit, balance (always in parens)
TXN_AMOUNTS_RE = re.compile(
    r"\s+(\([\d,]+\.\d{2}\)|[\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+\(([\d,]+\.\d{2})\)$"
)


def _to_float(s: str) -> float:
    return float(s.replace(',', '').replace('(', '').replace(')', ''))


def _parse_date(s: str) -> str:
    """Convert 'DD/MM/YYYY' → 'YYYY-MM-DD'."""
    return datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m-%d")


def _extract_lines(pdf_path: Path) -> List[str]:
    lines = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for ln in (page.extract_text() or "").splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(ln)
    return lines


def parse_adib_loan_statement(pdf_path: Path) -> Dict:
    """
    Parse an ADIB finance account statement PDF.

    Returns:
        account_no, statement_date, contract_signing_date, maturity_date,
        finance_amount, total_profit_amount,
        outstanding_principal, remaining_profit, total_outstanding,
        next_payment_amount, next_payment_date, remaining_installments,
        transactions: [{date, description, debit, credit, balance}]
    """
    lines = _extract_lines(pdf_path)

    # Extract header fields (last match wins — header repeats across pages)
    account_no = statement_date = contract_signing_date = maturity_date = None
    finance_amount = total_profit_amount = None
    outstanding_principal = remaining_profit = total_outstanding = None
    next_payment_amount = next_payment_date = None
    remaining_installments = None

    for ln in lines:
        if m := STMT_DATE_RE.search(ln):
            statement_date = _parse_date(m.group(1))
        if m := ACCOUNT_RE.search(ln):
            account_no = m.group(1).strip()
        if m := MATURITY_RE.search(ln):
            maturity_date = _parse_date(m.group(1))
        if m := SIGNING_RE.search(ln):
            contract_signing_date = _parse_date(m.group(1))
        if m := FINANCE_AMT_RE.search(ln):
            finance_amount = _to_float(m.group(1))
        if m := TOTAL_PROFIT_RE.search(ln):
            total_profit_amount = _to_float(m.group(1))
        if m := OUTSTANDING_PR_RE.search(ln):
            outstanding_principal = _to_float(m.group(1))
        if m := REMAINING_PRF_RE.search(ln):
            remaining_profit = _to_float(m.group(1))
        if m := TOTAL_OUTST_RE.search(ln):
            total_outstanding = _to_float(m.group(1))
        if m := NEXT_PAY_RE.search(ln):
            next_payment_amount = _to_float(m.group(1))
        if m := NEXT_DATE_RE.search(ln):
            next_payment_date = _parse_date(m.group(1))
        if m := REMAINING_INST_RE.search(ln):
            remaining_installments = int(m.group(1))

    # Parse transactions (deduplicated by identity)
    seen_txns: set = set()
    transactions: List[Dict] = []
    for ln in lines:
        date_m = TXN_START_RE.match(ln)
        if not date_m:
            continue
        amt_m = TXN_AMOUNTS_RE.search(ln)
        if not amt_m:
            continue
        txn_date = _parse_date(date_m.group(1))
        desc     = ln[date_m.end():amt_m.start()].strip()
        debit_s  = amt_m.group(1)
        credit   = _to_float(amt_m.group(2))
        balance  = _to_float(amt_m.group(3))
        is_debit = '(' in debit_s
        debit    = _to_float(debit_s)

        key = (txn_date, desc, debit, credit)
        if key in seen_txns:
            continue
        seen_txns.add(key)

        transactions.append({
            "date":     txn_date,
            "desc":     desc,
            "debit":    debit,
            "credit":   credit,
            "balance":  balance,
            "is_debit": is_debit,
        })

    return {
        "account_no":            account_no,
        "statement_date":        statement_date,
        "contract_signing_date": contract_signing_date,
        "maturity_date":         maturity_date,
        "finance_amount":        finance_amount,
        "total_profit_amount":   total_profit_amount,
        "outstanding_principal": outstanding_principal,
        "remaining_profit":      remaining_profit,
        "total_outstanding":     total_outstanding,
        "next_payment_amount":   next_payment_amount,
        "next_payment_date":     next_payment_date,
        "remaining_installments": remaining_installments,
        "transactions":          transactions,
    }


# ---------------------------------------------------------------------------
# Incremental ingestion helpers
# ---------------------------------------------------------------------------

def _stmt_id(account_no: str, statement_date: str) -> str:
    base = f"{account_no}|{statement_date}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _should_ingest(con: sqlite3.Connection, key: str, pdf_path: Path) -> bool:
    st = pdf_path.stat()
    row = con.execute(
        "SELECT mtime, size FROM ingested_files WHERE statement_file = ?", (key,)
    ).fetchone()
    if row is None:
        return True
    return int(row[0]) != int(st.st_mtime) or int(row[1]) != int(st.st_size)


def _mark_ingested(con: sqlite3.Connection, key: str, pdf_path: Path):
    st = pdf_path.stat()
    con.execute("""
        INSERT INTO ingested_files(statement_file, mtime, size, last_ingested_unixtime)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(statement_file) DO UPDATE SET
          mtime=excluded.mtime, size=excluded.size,
          last_ingested_unixtime=excluded.last_ingested_unixtime
    """, (key, int(st.st_mtime), int(st.st_size), int(time.time())))


def ingest_loans_dir(loans_dir: Path, db_path: Path) -> int:
    """
    Scan loans_dir for new/changed PDFs, parse each one, and upsert
    the statement summary into loan_statements. Returns files processed.
    """
    loans_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(loans_dir.glob("*.pdf"))
    processed = 0
    with sqlite3.connect(db_path) as con:
        for pdf in pdfs:
            key = f"loans/{pdf.name}"
            if not _should_ingest(con, key, pdf):
                continue
            try:
                stmt = parse_adib_loan_statement(pdf)
                if not stmt["statement_date"]:
                    log.warning("loan_parser: could not read statement date from %s", pdf.name)
                    continue

                sid = _stmt_id(stmt["account_no"] or pdf.stem, stmt["statement_date"])
                con.execute("""
                    INSERT INTO loan_statements (
                        id, statement_file, account_no, statement_date,
                        contract_signing_date, maturity_date,
                        finance_amount, total_profit_amount,
                        outstanding_principal, remaining_profit, total_outstanding,
                        next_payment_amount, next_payment_date,
                        remaining_installments, last_ingested_unixtime
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        statement_file=excluded.statement_file,
                        outstanding_principal=excluded.outstanding_principal,
                        remaining_profit=excluded.remaining_profit,
                        total_outstanding=excluded.total_outstanding,
                        next_payment_amount=excluded.next_payment_amount,
                        next_payment_date=excluded.next_payment_date,
                        remaining_installments=excluded.remaining_installments,
                        last_ingested_unixtime=excluded.last_ingested_unixtime
                """, (
                    sid, pdf.name, stmt["account_no"], stmt["statement_date"],
                    stmt["contract_signing_date"], stmt["maturity_date"],
                    stmt["finance_amount"], stmt["total_profit_amount"],
                    stmt["outstanding_principal"], stmt["remaining_profit"],
                    stmt["total_outstanding"], stmt["next_payment_amount"],
                    stmt["next_payment_date"], stmt["remaining_installments"],
                    int(time.time()),
                ))
                _mark_ingested(con, key, pdf)
                con.commit()
                processed += 1
                log.info(
                    "loan_parser: %s %s — outstanding=%.2f principal=%.2f profit=%.2f",
                    stmt["account_no"], stmt["statement_date"],
                    stmt["total_outstanding"] or 0,
                    stmt["outstanding_principal"] or 0,
                    stmt["remaining_profit"] or 0,
                )
            except Exception as e:
                log.error("loan_parser: error parsing %s: %s", pdf.name, e)
    return processed
