# FinShield

Educational banking & fraud analytics: FastAPI + Next.js + PostgreSQL (Neon). Three supervised fraud classifiers
(Logistic Regression, Random Forest, Histogram Gradient Boosting) plus KMeans customer segmentation. **Synthetic data only.**
Source of truth: `Banking_Fraud_Analytics_Implementation_Spec.md`.

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
