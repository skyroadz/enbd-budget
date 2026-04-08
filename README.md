# Budget Exporter

Self-hosted personal finance tracker for **Emirates NBD** customers. Parses PDF statements, categorises spending via ML, and serves a React dashboard with optional Prometheus/Grafana monitoring. Statements can be placed manually or fetched automatically from Outlook (optional).

**Supported statements**

| Bank | Type | Support |
|---|---|---|
| Emirates NBD | Credit Card | ✅ |
| Emirates NBD | Chequing | ✅ |
| Emirates NBD | Savings | ✅ |
| ADIB | Loans | ⚙️ Optional |

**Stack:** Python 3.12 · FastAPI · SQLite · React 18 · scikit-learn · Prometheus · Grafana · Docker Compose

---

## How It Works

### Statement fetcher *(optional)*
Enabled via the `fetcher` profile. Runs on a cron schedule (daily, 10am). Authenticates with Microsoft Graph via device-code flow, downloads ENBD PDFs, unlocks them with your PDF password, routes them to the right directory, and triggers backend ingestion. Without it, drop PDFs manually into the appropriate `data/` subdirectory.

### Backend ingestion
Scans statement directories for new/changed PDFs on every `/metrics` request or `POST /admin/recategorize`. Parses transactions, cleans merchant names, then sends them to the ML model for categorisation.

### ML categorisation
An `ml-trainer` service trains a scikit-learn classifier on your labelled transactions. Once enough labelled data exists, new transactions are auto-categorised if the model's confidence exceeds the configured threshold (`ML_CONFIDENCE_THRESHOLD`, default `0.6`). The model retrains incrementally as you label more data.

### Monitoring (optional)
Prometheus scrapes `/metrics` every 30 seconds. Two pre-built Grafana dashboards are provisioned automatically:
- **personal-spend** — category totals, trends, top merchants (Prometheus-based)
- **budget-exporter** — detailed spend breakdown (Infinity datasource)

---

## Setup

### Prerequisites
- Docker 24+ with Compose v2
- An Azure app registration with `Mail.Read` on a personal Microsoft account to retrieve statements from your email (Optional)

> **Azure setup (one-time):** Register an app at portal.azure.com → API permissions → Microsoft Graph → Delegated → `Mail.Read`. Under Authentication, enable **Allow public client flows**.

### 1. Clone & configure

```bash
git clone <repo-url> budget-exporter && cd budget-exporter
```

Create `.env`:
```env
# Optional
AZURE_CLIENT_ID=your-azure-client-id
PDF_PASSWORD=your-pdf-password        # usually your DOB as DDMMYYYY

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GRAFANA_PASSWORD=admin                # change this
```

### 2. Create data directories

```bash
mkdir -p data/statements data/savings data/chequing data/loans
```

### 3. Start services

**Core only** (place PDFs manually — `data/statements` for credit card, `data/chequing` for chequing account, `data/savings` for savings account):
```bash
docker compose up --build -d
```

**With automatic statement fetcher:**
```bash
docker compose --profile fetcher up --build -d
```

**With Prometheus + Grafana:**
```bash
docker compose --profile monitoring up --build -d
```

**Everything:**
```bash
docker compose --profile fetcher --profile monitoring up --build -d
```

| Service | URL | Profile |
|---|---|---|
| Frontend | http://localhost:3000 | always on |
| Backend | http://localhost:8000 | always on |
| Grafana | http://localhost:3001 | `monitoring` |
| Prometheus | http://localhost:9090 | `monitoring` |
| Statement fetcher | *(no port)* | `fetcher` |

### 4. Authenticate the fetcher (one-time, fetcher profile only)

```bash
docker compose --profile fetcher run --rm statement-fetcher python fetch.py
```

Follow the device-code prompt in your browser. The token is cached in `data/token_cache.json` and refreshes automatically.

---

## Categorisation & ML

Categorisation is handled entirely by the ML model. New transactions are auto-categorised if the model's confidence meets the threshold (`ML_CONFIDENCE_THRESHOLD`, default `0.6`). Below the threshold they land as `"uncategorized"` for manual labelling.

**The ML tab in the React UI lets you:**
- Review all uncategorised merchants and assign them a category
- Override any merchant to a specific category (locks it against future ML changes)
- Trigger a model retrain after labelling new data

The more you label, the better the model gets. Locked transactions are never overwritten by retrains.

**Priority (highest → lowest):**
1. ML model prediction (if confidence ≥ threshold)
2. `"uncategorized"` fallback

---

## Monitoring

When started with `--profile monitoring`, Grafana boots with:
- **Prometheus** datasource pre-wired to `http://prometheus:9090`
- **Infinity** datasource plugin pre-installed in the image
- Both dashboards in `grafana/` provisioned automatically on startup

Default login: `admin` / value of `GRAFANA_PASSWORD` (default: `admin`).

---

## Key API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/metrics` | Prometheus metrics + triggers ingestion |
| `GET` | `/transactions` | Paginated transaction list |
| `PATCH` | `/transactions/{id}/category` | Override + lock a transaction category |
| `GET` | `/api/summary/monthly` | Monthly spend by category |
| `POST` | `/api/budget` | Set a monthly budget limit |
| `POST` | `/admin/recategorize` | Force re-categorise all transactions |
| `GET` | `/admin/uncategorized` | List unlabelled merchants |

---

## Useful Commands

```bash
# Fetch statements now
docker compose run --rm statement-fetcher python fetch.py

# Force re-ingest + re-categorise
curl -X POST http://localhost:8000/admin/recategorize

# Rebuild after code changes
docker compose --profile monitoring up --build -d

# Rebuild a single service
docker compose build --no-cache budget-exporter && docker compose up -d budget-exporter

# Tail logs
docker compose logs -f budget-exporter
docker compose logs -f grafana

# Backup the database
cp data/state.db data/state.db.bak
```

---

## Directory Layout

```
budget-exporter/
├── app/                    # FastAPI backend (ingestion, rules, API routes)
├── parsers/                # Bank-specific PDF parsers (ENBD, ADIB)
├── fetcher/                # Statement downloader (Graph API + Telegram)
├── ml-trainer/             # scikit-learn training + prediction service
├── frontend/               # React 18 + Vite + Tailwind dashboard
├── grafana/
│   ├── budget-exporter.json    # Infinity-based spending dashboard
│   ├── personal-spend.json     # Prometheus-based spending dashboard
│   ├── Dockerfile              # Grafana image with Infinity plugin pre-installed
│   └── provisioning/           # Auto-wired datasources + dashboard loader
├── prometheus/
│   └── prometheus.yml          # Scrape config targeting budget-exporter:8000/metrics
├── tools/                  # Maintenance scripts (uncategorized, reclassify, etc.)
├── data/                   # git-ignored; statements + SQLite DB live here
├── docker-compose.yml
└── .env                    # Your secrets — never commit this
```

---

## Data Privacy

Everything is stored locally in `data/state.db`. No data leaves your machine. The `data/` directory is git-ignored.
