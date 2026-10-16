# FinShield

Educational banking & fraud analytics: FastAPI + Next.js + PostgreSQL (Neon). Three supervised fraud classifiers
(Logistic Regression, Random Forest, Histogram Gradient Boosting) plus KMeans customer segmentation. **Synthetic data only.**
Source of truth: `Banking_Fraud_Analytics_Implementation_Spec.md`.

## Quick start on a new machine (nothing to sign up for)
Needs **Python 3.12+** and **Node 20+**. The database and trained models are *not* stored in git (they are generated files);
they are rebuilt deterministically (seed 42, identical checksum) on first run, in about 4 minutes.

Windows (PowerShell):
```powershell
git clone https://github.com/AdityaPatra1947/FinSHIELD.git; cd FinSHIELD
.\scripts\run-local.ps1 -Local
```
macOS / Linux:
```bash
git clone https://github.com/AdityaPatra1947/FinSHIELD.git && cd FinSHIELD
bash scripts/run-local.sh
```
Open http://localhost:3000 and sign in with a demo account (table below). Everything runs offline on SQLite; Neon/PostgreSQL is
optional (put `DATABASE_URL` in `backend/.env`, see `backend/.env.example`, and omit `-Local`).
## Run locally
```powershell
.\scripts\run-local.ps1
```
Open http://localhost:3000. API docs: http://localhost:8000/api/v1/docs.

Database: `backend/.env` (git-ignored) holds `DATABASE_URL` (Neon pooled) and `MIGRATION_DATABASE_URL` (Neon direct).
With `DATABASE_URL` unset the app falls back to a local SQLite file. TLS (`sslmode=require` or stronger) is enforced.

## Logins
`python -m app.cli seed-users` (re)creates these demo accounts with fixed, deliberately simple passwords (also listed in `artifacts/demo_credentials.txt`). They are for local use with synthetic data only; change or deactivate them in Admin > Users before exposing the app anywhere.

| Role | Email | Password |
|---|---|---|
| admin | admin@gmail.com | admin123 |
| analyst | analyst@gmail.com | analyst123 |
| customer (CUST-0001) | customer1@gmail.com | customer123 |
| customer (CUST-0002) | customer2@gmail.com | customer123 |
| customer (CUST-0003) | customer3@gmail.com | customer123 |

| Role | Can do |
|---|---|
| customer | own spending, own transactions, add manual transactions |
| analyst | + organization dashboard, fraud queue, model comparison, customer segments |
| admin | + retrain/recluster/regenerate jobs, model promotion & rollback, users, audit log |

## CLI (backend/, venv active)
`app db-upgrade` · `app seed-users` · `app dataset-build` · `app train` · `app cluster` · `app config-check` · `python -m app.ml.pipeline all`

## Security implemented
Argon2id passwords; opaque 256-bit session tokens (HMAC-hashed in DB, HttpOnly cookie, 30-min idle / 12-h absolute);
double-submit + session-bound CSRF and Origin checks on every mutation; login CSRF; generic login errors; login rate limit
(in-process); server-side role guards and customer ownership (cross-customer access returns 404); idempotent transaction creation;
append-only audit events; no stack traces/DSNs in errors; redacted config check.

## Honest status vs. the spec
Built: everything above, seeded synthetic ledger (600 customers, ~197k transactions, ~0.8% fraud), point-in-time features,
temporal protocol with label maturity, 3 models with calibration/threshold policy/locked test, KMeans, spending formulas
(worked-fixture test), dashboards, admin operations, audit.

Not built yet: Alembic migrations (tables are created from SQLAlchemy metadata), PostgreSQL row-level security and composite
tenant foreign keys, CSV import wizard, duplicate-evidence layer, refund/transfer link APIs, budgets, recurring detection,
customer disputes/labels, shared-store rate limiting, CI/secret scanning. Retrain jobs run as a local subprocess (not a durable
leased queue). Timestamps in new tables are epoch integers. Because the database credentials were pasted into a chat,
rotate that Neon password when you are done.

## Personal-finance tracker (My money)
All 600 customers have a structured finance profile: accounts (bank, savings, cash, card), typed transactions
(income / expense / transfer / investment / debt) with category + subcategory, merchant, payment method, tags, notes,
recurring and fixed/variable flags and need/want, plus income types with gross vs net, recurring items, budgets
(80% / 100% alerts), goals, loans with EMI amortisation, credit cards, investments with monthly valuations, tax
summary, insights (forecast, unusual purchases, budget overshoot) and income brackets with simple / advanced modes.
**Every number is clickable and explains its formula, the exact inputs, what it means and how to read it.**

Key rules: transfers, ATM withdrawals, card-bill payments, investments and loan principal are never spending (no
double counting); only the interest part of an EMI is an expense. Payments to other people stay "to classify" until you
pick a category. Bank entries are immutable evidence (reclassify only); your own manual entries can be voided.

Build / rebuild the finance layer: `python -m app.finance.enrich` (deterministic, seed 777). Verified by
`pytest backend/tests/unit/test_finance_calcs.py` (hand-checked fixture) and `python backend/tests/e2e_finance.py`.

## Local mode (no cloud database)
Set `FINSHIELD_LOCAL=1` to run against a self-contained SQLite database and `artifacts/local/` (never touches Neon or its
model files):
```powershell
$env:FINSHIELD_LOCAL = "1"
cd backend
.\.venv\Scripts\python.exe -m app.ml.pipeline all     # data + finance layer + 3 models + clusters (~3 min)
.\.venv\Scripts\python.exe -m app.cli seed-users
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```
Neon's free tier suspends idle databases (1-2 minute cold starts) and bulk transfers can be slow on some networks; local mode
avoids that for development and demos.