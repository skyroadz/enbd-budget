"""
Central configuration: paths, environment variable overrides, compiled regexes, logging.
"""
import logging
import os
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Project root is one level above this file (app/config.py → project root)
APP_DIR = Path(__file__).parent.parent

DATA_DIR       = Path(os.getenv("DATA_DIR",       str(APP_DIR / "data")))
STATEMENTS_DIR = Path(os.getenv("STATEMENTS_DIR", str(DATA_DIR / "statements")))
CHEQUING_DIR   = Path(os.getenv("CHEQUING_DIR",   str(DATA_DIR / "chequing")))
SAVINGS_DIR    = Path(os.getenv("SAVINGS_DIR",    str(DATA_DIR / "savings")))
LOANS_DIR      = Path(os.getenv("LOANS_DIR",      str(DATA_DIR / "loans")))
DB_PATH        = Path(os.getenv("DB_PATH",        str(DATA_DIR / "state.db")))
RULES_PATH     = Path(os.getenv("RULES_PATH",     str(APP_DIR / "rules.yaml")))
ML_MODEL_PATH  = Path(os.getenv("ML_MODEL_PATH",  str(APP_DIR / "models" / "categorizer.pkl")))
ML_CONFIDENCE_THRESHOLD = float(os.getenv("ML_CONFIDENCE_THRESHOLD", "0.8"))

# ---------------------------------------------------------------------------
# Credit card statement regexes
# ---------------------------------------------------------------------------

# Typical transaction row: 02/01/2026 03/01/2026 CAREEM RIDE DUBAI ARE 43.99
TXN_RE = re.compile(
    r"^(?P<txn_date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<post_date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<amount>[\d,]+\.\d{2})(?P<cr>CR)?$"
)

# Detect FX in description (e.g., "... 21.00 USD")
FX_IN_DESC_RE   = re.compile(r".*\s(?P<orig_amount>\d+(?:\.\d+)?)\s(?P<orig_ccy>[A-Z]{3})\s*$")
AED_RATE_LINE_RE = re.compile(r"^\(1 AED = .+\)$")

STOP_RE        = re.compile(r"^STATEMENT SUMMARY\b", re.IGNORECASE)
SUPP_RE        = re.compile(r"^Supplementary Card Number\b", re.IGNORECASE)
INSTALLMENT_RE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+INSTALLMENT PLAN EMI\b", re.IGNORECASE)
