"""Pipeline stages, all reading/writing the configured database (Neon PostgreSQL or SQLite fallback).

generate_dataset -> train_models -> recluster.  `python -m app.ml.pipeline [all|data|train|cluster]`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.db import ART, get_engine, init_db, kv_get, kv_set
from app.ml import clustering, features, generator, train


def _copy_method(table, conn, keys, data_iter):
    """Fast bulk load for PostgreSQL (COPY); pandas converts NaN -> None before this point."""
    cols = ", ".join(f'"{k}"' for k in keys)
    with conn.connection.cursor() as cur:
        with cur.copy(f'COPY "{table.name}" ({cols}) FROM STDIN') as cp:
            for row in data_iter:
                cp.write_row(row)


def _write(df: pd.DataFrame, name: str) -> None:
    eng = get_engine()
    pg = eng.dialect.name == "postgresql"
    df.to_sql(name, eng, if_exists="replace", index=False, chunksize=20000,
              method=_copy_method if pg else None)


def reason_codes(r: pd.Series) -> list[str]:
    out = []
    v = r.get("amount_vs_median30")
    if v == v and v is not None and v > 3:
        out.append("amount above prior 30-day median")
    if r.get("payee_new") == 1 and (r.get("n_ok_24h", 0) or 0) >= 2:
        out.append("new payee plus high recent activity")
    elif r.get("payee_new") == 1:
        out.append("new payee")
    if r.get("device_new") == 1:
        out.append("new device")
    if (r.get("n_fail_24h", 0) or 0) >= 1:
        out.append("recent failed attempts")
    return out or ["no single dominant signal (contextual signals only)"]


def generate_dataset(customers: int = 600, seed: int = 42, log=print) -> dict:
    init_db()
    log("generating synthetic ledger ...")
    cust, tx, labels, manifest = generator.generate(customers, 365, seed)
    log(f"  {len(tx):,} transactions, {len(labels):,} labeled decisions, {manifest['fraud_positives']} fraud")
    tx = tx.drop(columns=["scale"], errors="ignore")
    for name, df in (("customers", cust), ("transactions", tx), ("fraud_labels", labels)):
        log(f"  writing {name} ({len(df):,} rows) ...")
        _write(df, name)
    with get_engine().begin() as c:
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_tx_cust ON transactions(customer_id, posted_ts)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_tx_id ON transactions(id)"))
        c.execute(text("DROP TABLE IF EXISTS fraud_scores"))
    kv_set("dataset_manifest", manifest)
    for k in ("latest_run", "latest_clusters"):
        with get_engine().begin() as c:
            c.execute(text("DELETE FROM results WHERE key=:k"), {"k": k})
    return manifest


def _load():
    eng = get_engine()
    tx = pd.read_sql("SELECT * FROM transactions", eng)
    for c in ("eligible", "is_derived"):
        tx[c] = tx[c].astype(bool)
    cust = pd.read_sql("SELECT customer_id, open_day FROM customers", eng)
    labels = pd.read_sql("SELECT id, label, available_ts FROM fraud_labels", eng)
    return tx, cust, labels


def train_models(log=print) -> dict:
    manifest = kv_get("dataset_manifest")
    if not manifest:
        raise SystemExit("no dataset: run the data stage first")
    tx, cust, labels = _load()
    open_ts = {int(r.customer_id): generator.ORIGIN_TS + (int(r.open_day) - 1) * generator.DAY for r in cust.itertuples()}
    log("building point-in-time features ...")
    feats = features.build_features(tx, open_ts)
    log(f"  {len(feats):,} decision rows")
    run, arts, parts = train.run_experiment(feats, labels, ART, manifest, log)
    if run["status"] != "completed":
        kv_set("latest_run", run)
        raise SystemExit(f"run invalid: {run['problems']}")
    train.write_reports(run, ART / "results")
    test = parts["test"]
    sc = pd.DataFrame({"txn_id": test.index, **{f: arts[f][0].predict_proba(arts[f][1](test))[:, 1] for f in train.FAMILIES}})
    sc["reasons"] = [json.dumps(reason_codes(r)) for _, r in test[features.ALLOWLIST].iterrows()]
    sc["scored_at"] = int(time.time())
    _write(sc, "fraud_scores")
    with get_engine().begin() as c:
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_sc ON fraud_scores(txn_id)"))
    kv_set("latest_run", run)
    return run


def recluster(log=print) -> dict:
    eng = get_engine()
    tx = pd.read_sql("SELECT customer_id,status,posted_ts,purpose,direction,category,account_kind,amount_minor FROM transactions", eng)
    as_of = generator.ORIGIN_TS + 365 * generator.DAY
    log("clustering ...")
    clus = clustering.run_clustering(tx, as_of, 42)
    kv_set("latest_clusters", clus)
    return clus


def build_all(customers: int = 600, seed: int = 42, log=print) -> None:
    t0 = time.time()
    generate_dataset(customers, seed, log)
    train_models(log)
    recluster(log)
    log(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    {"all": build_all, "data": generate_dataset, "train": train_models, "cluster": recluster}[stage]()
