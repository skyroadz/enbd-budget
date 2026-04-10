"""
ENBD statement fetcher.
Supports two mail providers:
  - outlook (default): Microsoft Graph API with MSAL device code flow
  - gmail: Google Gmail API with OAuth2 installed-app flow

Environment variables (common):
  MAIL_PROVIDER         "outlook" (default) or "gmail"
  PDF_PASSWORD          required
  BUDGET_API_URL        default: http://budget-exporter:8000
  TELEGRAM_BOT_TOKEN    optional
  TELEGRAM_CHAT_ID      optional
  DATA_DIR              root directory for statement subdirs (default: /data)
  EMAIL_SENDER_FILTER   sender address substring to filter on (default: statement@emiratesnbd.com)
  ACCOUNT_ROUTES        comma-separated list of keyword:subdir pairs
                        default: "credit card:statements,savings account:savings,current account:chequing"

  Outlook-specific:
  AZURE_CLIENT_ID       required when MAIL_PROVIDER=outlook
  TOKEN_CACHE           path to token cache file (default: /data/token_cache.json)

  Gmail-specific:
  GOOGLE_CREDENTIALS_FILE  path to OAuth2 client credentials JSON from Google Cloud Console
                           (default: /data/gmail_credentials.json)
  GOOGLE_TOKEN_FILE        path to cached OAuth2 token (default: /data/gmail_token.json)
"""

import os
import io
import base64
import logging
import requests
import pikepdf
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Common config ─────────────────────────────────────────────────────────────

MAIL_PROVIDER     = os.environ.get("MAIL_PROVIDER", "outlook").lower()
PDF_PASSWORD      = os.environ["PDF_PASSWORD"]
BUDGET_API_URL    = os.environ.get("BUDGET_API_URL", "http://budget-exporter:8000")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
DATA_DIR          = Path(os.environ.get("DATA_DIR", "/data"))
EMAIL_SENDER_FILTER = os.environ.get("EMAIL_SENDER_FILTER", "statement@emiratesnbd.com")

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


# ── Outlook config / auth ─────────────────────────────────────────────────────

if MAIL_PROVIDER == "outlook":
    import msal

    CLIENT_ID   = os.environ["AZURE_CLIENT_ID"]
    TOKEN_CACHE = Path(os.environ.get("TOKEN_CACHE", "/data/token_cache.json"))

    GRAPH_SCOPES = ["Mail.Read"]
    AUTHORITY    = "https://login.microsoftonline.com/consumers"

    def _load_cache() -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if TOKEN_CACHE.exists():
            cache.deserialize(TOKEN_CACHE.read_text())
        return cache

    def _save_cache(cache: msal.SerializableTokenCache):
        if cache.has_state_changed:
            TOKEN_CACHE.write_text(cache.serialize())
            TOKEN_CACHE.chmod(0o600)

    def get_outlook_token() -> str:
        cache = _load_cache()
        app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                _save_cache(cache)
                return result["access_token"]

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


# ── Gmail config / auth ───────────────────────────────────────────────────────

if MAIL_PROVIDER == "gmail":
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as google_build

    GOOGLE_CREDENTIALS_FILE = Path(
        os.environ.get("GOOGLE_CREDENTIALS_FILE", "/data/gmail_credentials.json")
    )
    GOOGLE_TOKEN_FILE = Path(
        os.environ.get("GOOGLE_TOKEN_FILE", "/data/gmail_token.json")
    )
    GMAIL_AUTH_PORT = int(os.environ.get("GMAIL_AUTH_PORT", "8081"))
    GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def get_gmail_service():
        creds = None

        if GOOGLE_TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
            else:
                if not GOOGLE_CREDENTIALS_FILE.exists():
                    raise RuntimeError(
                        f"Gmail credentials file not found: {GOOGLE_CREDENTIALS_FILE}\n"
                        "Download it from Google Cloud Console → APIs & Services → Credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(GOOGLE_CREDENTIALS_FILE), GMAIL_SCOPES
                )
                # open_browser=False so this works headless inside Docker.
                # The redirect lands on port GMAIL_AUTH_PORT (must be exposed/forwarded).
                print("\n" + "=" * 60)
                print("ACTION REQUIRED: Open the URL that appears below in your")
                print(f"browser. Make sure port {GMAIL_AUTH_PORT} is reachable on this host.")
                print("=" * 60 + "\n")
                creds = flow.run_local_server(host="localhost", bind_addr="0.0.0.0", port=GMAIL_AUTH_PORT, open_browser=False)

            GOOGLE_TOKEN_FILE.write_text(creds.to_json())
            GOOGLE_TOKEN_FILE.chmod(0o600)
            log.info(f"Gmail token saved to {GOOGLE_TOKEN_FILE}")

        return google_build("gmail", "v1", credentials=creds)


# ── Shared helpers ────────────────────────────────────────────────────────────

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


# ── Outlook fetching ──────────────────────────────────────────────────────────

def graph_get(token: str, url: str, params: dict = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


def fetch_emails_outlook() -> list[dict]:
    """
    Returns a list of dicts:
      { "subject": str, "attachments": [{"name": str, "bytes": bytes}] }
    """
    token = get_outlook_token()
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
    raw_emails = []
    while url:
        data = graph_get(token, url, params)
        raw_emails.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None

    log.info(f"Found {len(raw_emails)} Outlook email(s) with attachments.")

    emails = []
    for email in raw_emails:
        subject = email.get("subject", "")
        att_data = graph_get(
            token,
            f"https://graph.microsoft.com/v1.0/me/messages/{email['id']}/attachments",
        )
        pdf_atts = [
            a for a in att_data.get("value", [])
            if a.get("name", "").lower().endswith(".pdf")
        ]
        if not pdf_atts:
            continue
        attachments = []
        for att in pdf_atts:
            raw = graph_get(
                token,
                f"https://graph.microsoft.com/v1.0/me/messages/{email['id']}/attachments/{att['id']}",
            )
            attachments.append({
                "name": att["name"],
                "bytes": base64.b64decode(raw["contentBytes"]),
            })
        emails.append({"subject": subject, "attachments": attachments})

    return emails


# ── Gmail fetching ────────────────────────────────────────────────────────────

def _gmail_get_pdf_parts(payload: dict) -> list[dict]:
    """Recursively collect PDF parts from a Gmail message payload."""
    parts = []
    for part in payload.get("parts", []):
        filename = part.get("filename", "")
        if filename.lower().endswith(".pdf"):
            parts.append(part)
        elif part.get("parts"):
            parts.extend(_gmail_get_pdf_parts(part))
    return parts


def fetch_emails_gmail() -> list[dict]:
    """
    Returns a list of dicts:
      { "subject": str, "attachments": [{"name": str, "bytes": bytes}] }
    """
    service = get_gmail_service()
    query = f"from:{EMAIL_SENDER_FILTER} has:attachment"
    results = service.users().messages().list(userId="me", q=query, maxResults=500).execute()
    messages = results.get("messages", [])
    log.info(f"Found {len(messages)} Gmail message(s) matching query.")

    emails = []
    for i, msg_ref in enumerate(messages, 1):
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        # Extract subject from headers
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "")
        log.info(f"[{i}/{len(messages)}] {subject!r}")

        pdf_parts = _gmail_get_pdf_parts(msg.get("payload", {}))
        if not pdf_parts:
            continue

        attachments = []
        for part in pdf_parts:
            att_id = part["body"].get("attachmentId")
            if att_id:
                att = service.users().messages().attachments().get(
                    userId="me", messageId=msg_ref["id"], id=att_id
                ).execute()
                # Gmail uses URL-safe base64
                pdf_bytes = base64.urlsafe_b64decode(att["data"] + "==")
            elif part["body"].get("data"):
                pdf_bytes = base64.urlsafe_b64decode(part["body"]["data"] + "==")
            else:
                log.warning(f"No data for attachment {part.get('filename')} — skipping.")
                continue

            attachments.append({"name": part["filename"], "bytes": pdf_bytes})

        if attachments:
            emails.append({"subject": subject, "attachments": attachments})

    return emails


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info(f"Starting ENBD statement fetcher (provider: {MAIL_PROVIDER}).")

    if MAIL_PROVIDER == "outlook":
        emails = fetch_emails_outlook()
    elif MAIL_PROVIDER == "gmail":
        emails = fetch_emails_gmail()
    else:
        raise RuntimeError(f"Unknown MAIL_PROVIDER: {MAIL_PROVIDER!r}. Use 'outlook' or 'gmail'.")

    # Build a set of already-saved filenames per directory to avoid re-downloading
    saved_per_dir: dict[Path, set[str]] = {
        directory: existing_filenames(directory)
        for _, directory in ACCOUNT_ROUTES
    }

    saved = 0
    saved_files: list[str] = []

    for email in emails:
        subject = email["subject"]
        dest_dir = dest_dir_for_subject(subject)
        if dest_dir is None:
            log.info(f"Skipping unrecognised subject: {subject!r}")
            continue

        for att in email["attachments"]:
            filename = att["name"]
            if filename in saved_per_dir[dest_dir]:
                log.info(f"Already exists, skipping: {dest_dir.name}/{filename}")
                continue

            log.info(f"Unlocking [{dest_dir.name}]: {filename}")
            try:
                unlocked = unlock_pdf(att["bytes"], PDF_PASSWORD)
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
