"""
ENBD statement fetcher.
- Authenticates with Microsoft Graph API (device code flow, token cached)
- Fetches credit card, savings, and chequing statements from Outlook
- Unlocks password-protected PDFs and routes each to the correct directory
- Triggers budget-exporter ingestion via API

Environment variables:
  AZURE_CLIENT_ID       required
  PDF_PASSWORD          required
  TOKEN_CACHE           path to token cache file (default: /data/token_cache.json)
  BUDGET_API_URL        default: http://budget-exporter:8000
  TELEGRAM_BOT_TOKEN    optional
  TELEGRAM_CHAT_ID      optional
  DATA_DIR              root directory for statement subdirs (default: /data)
  EMAIL_SENDER_FILTER   sender address substring to filter on (default: statement@emiratesnbd.com)
  ACCOUNT_ROUTES        comma-separated list of keyword:subdir pairs
                        default: "credit card:statements,savings account:savings,current account:chequing"
                        example: "credit card:statements,mastercard:statements,savings account:savings"
"""

import os
import io
import base64
import logging
import requests
import pikepdf
from pathlib import Path

import msal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config (set via environment variables) ────────────────────────────────────
CLIENT_ID         = os.environ["AZURE_CLIENT_ID"]
PDF_PASSWORD      = os.environ["PDF_PASSWORD"]
TOKEN_CACHE       = Path(os.environ.get("TOKEN_CACHE", "/data/token_cache.json"))
BUDGET_API_URL    = os.environ.get("BUDGET_API_URL", "http://budget-exporter:8000")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

EMAIL_SENDER_FILTER = os.environ.get("EMAIL_SENDER_FILTER", "statement@emiratesnbd.com")

# Maps a substring of the email subject → destination directory.
# Keywords are lowercased and matched against the lowercased subject.
# Configurable via ACCOUNT_ROUTES env var: "keyword:subdir,keyword:subdir"
_ROUTES_DEFAULT = "credit card:statements,savings account:savings,current account:chequing"

def _parse_routes(raw: str) -> list[tuple[str, Path]]:
    routes = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            log.warning(f"Ignoring malformed ACCOUNT_ROUTES entry (no colon): {entry!r}")
            continue
        keyword, subdir = entry.split(":", 1)
        keyword = keyword.strip().lower()
        subdir = subdir.strip()
        if not keyword or not subdir:
            log.warning(f"Ignoring empty keyword or subdir in ACCOUNT_ROUTES entry: {entry!r}")
            continue
        routes.append((keyword, DATA_DIR / subdir))
    return routes

ACCOUNT_ROUTES = _parse_routes(os.environ.get("ACCOUNT_ROUTES", _ROUTES_DEFAULT))

if not ACCOUNT_ROUTES:
    raise RuntimeError("ACCOUNT_ROUTES is empty or invalid — cannot continue.")

GRAPH_SCOPES = ["Mail.Read"]
AUTHORITY    = "https://login.microsoftonline.com/consumers"


# ── Auth ──────────────────────────────────────────────────────────────────────

def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE.exists():
        cache.deserialize(TOKEN_CACHE.read_text())
    return cache


def _save_cache(cache: msal.SerializableTokenCache):
    if cache.has_state_changed:
        TOKEN_CACHE.write_text(cache.serialize())
        TOKEN_CACHE.chmod(0o600)


def get_access_token() -> str:
    cache = _load_cache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            return result["access_token"]

    # First run or token expired — device code flow
    flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to create device flow: {flow}")

    print("\n" + "=" * 60)
    print("ACTION REQUIRED: Open the URL below and enter the code.")
    print(f"  URL  : {flow['verification_uri']}")
    print(f"  Code : {flow['user_code']}")
    print("=" * 60 + "\n")

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description')}")

    _save_cache(cache)
    return result["access_token"]


# ── Graph API helpers ─────────────────────────────────────────────────────────

def graph_get(token: str, url: str, params: dict = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


# ── Core logic ────────────────────────────────────────────────────────────────

def dest_dir_for_subject(subject: str) -> Path | None:
    """Return the destination directory based on email subject, or None if unrecognised."""
    subject_lower = subject.lower()
    for keyword, directory in ACCOUNT_ROUTES:
        if keyword in subject_lower:
            return directory
    return None


def existing_filenames(directory: Path) -> set[str]:
    directory.mkdir(parents=True, exist_ok=True)
    return {p.name for p in directory.glob("*.pdf")}


def fetch_enbd_emails(token: str) -> list[dict]:
    """Return ENBD statement emails with attachments, filtered by sender only.
    Subject routing is handled in Python so subject line changes don't break fetching."""
    filter_q = (
        f"contains(from/emailAddress/address, '{EMAIL_SENDER_FILTER}')"
        f" and hasAttachments eq true"
    )
    url = "https://graph.microsoft.com/v1.0/me/messages"
    params = {
        "$filter": filter_q,
        "$select": "id,subject,receivedDateTime",
        "$top": 999,
    }
    results = []
    while url:
        data = graph_get(token, url, params)
        results.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None  # nextLink has params baked in
    return results


def get_pdf_attachments(token: str, message_id: str) -> list[dict]:
    data = graph_get(
        token,
        f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments",
    )
    all_atts = data.get("value", [])
    return [a for a in all_atts if a.get("name", "").lower().endswith(".pdf")]


def download_attachment(token: str, message_id: str, attachment_id: str) -> bytes:
    data = graph_get(
        token,
        f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments/{attachment_id}",
    )
    return base64.b64decode(data["contentBytes"])


def unlock_pdf(pdf_bytes: bytes, password: str) -> bytes:
    with pikepdf.open(io.BytesIO(pdf_bytes), password=password) as pdf:
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()


def trigger_ingestion():
    try:
        resp = requests.post(f"{BUDGET_API_URL}/admin/recategorize", timeout=30)
        resp.raise_for_status()
        log.info("Ingestion triggered successfully.")
    except Exception as e:
        log.warning(f"Failed to trigger ingestion: {e}")


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("Telegram notification sent.")
    except Exception as e:
        log.warning(f"Failed to send Telegram notification: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("Starting ENBD statement fetcher.")
    token = get_access_token()

    # Build a set of already-saved filenames per directory to avoid re-downloading
    saved_per_dir: dict[Path, set[str]] = {
        directory: existing_filenames(directory)
        for _, directory in ACCOUNT_ROUTES
    }

    emails = fetch_enbd_emails(token)
    log.info(f"Found {len(emails)} ENBD email(s) with attachments.")

    saved = 0
    saved_files: list[str] = []
    for email in emails:
        subject = email.get("subject", "")
        dest_dir = dest_dir_for_subject(subject)
        if dest_dir is None:
            log.info(f"Skipping unrecognised subject: {subject!r}")
            continue

        attachments = get_pdf_attachments(token, email["id"])
        for att in attachments:
            filename = att["name"]
            if filename in saved_per_dir[dest_dir]:
                log.info(f"Already exists, skipping: {dest_dir.name}/{filename}")
                continue

            log.info(f"Downloading [{dest_dir.name}]: {filename}")
            pdf_bytes = download_attachment(token, email["id"], att["id"])

            log.info(f"Unlocking: {filename}")
            try:
                unlocked = unlock_pdf(pdf_bytes, PDF_PASSWORD)
            except pikepdf.PasswordError:
                log.error(f"Wrong password for {filename} — skipping.")
                continue

            dest = dest_dir / filename
            dest.write_bytes(unlocked)
            log.info(f"Saved: {dest}")
            saved_per_dir[dest_dir].add(filename)
            saved += 1
            saved_files.append(f"{dest_dir.name}/{filename}")

    log.info(f"Done. {saved} new statement(s) saved.")

    if saved > 0:
        trigger_ingestion()
        file_list = "\n".join(f"• `{f}`" for f in saved_files)
        send_telegram(
            f"*Budget Exporter* — {saved} new statement(s) ingested\n\n{file_list}"
        )


if __name__ == "__main__":
    main()