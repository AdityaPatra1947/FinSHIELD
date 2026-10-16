"""Build the finance layer and write every table to the configured database.

Source of the base ledger:
  * default: regenerate it deterministically from the stored dataset manifest (seed/customers) and verify the SHA-256
    against the manifest, so nothing large has to be downloaded from a remote database;
  * `--from-db`: read the ledger back from the database instead.
"""
from __future__ import annotations

import sys
import time

import pandas as pd
from sqlalchemy import text

from app.db import get_engine, init_db, kv_get, kv_set, wait_ready
from app.finance import layer


def _base_from_manifest(log) -> tuple[pd.DataFrame, pd.DataFrame]:
    from app.ml import generator

    man = kv_get("dataset_manifest")
    if not man:
        raise SystemExit("no dataset manifest in the database: run the data stage first")
    log(f"regenerating base ledger (seed {man['seed']}, {man['customers']} customers) ...")
    cust, tx, _labels, new_man = generator.generate(int(man["customers"]), int(man["event_days"]), int(man["seed"]))
    if new_man["sha256"] != man["sha256"]:
        raise SystemExit("regenerated ledger does not match the stored dataset checksum; use --from-db instead")
    log("  checksum verified: identical to the dataset already in the database")
    return cust, tx.drop(columns=["scale"], errors="ignore")


def _base_from_db(log) -> tuple[pd.DataFrame, pd.DataFrame]:
    eng = get_engine()
    log("reading ledger from the database ...")
    tx = pd.read_sql("SELECT * FROM transactions", eng)
    for c in ("eligible", "is_derived"):
        tx[c] = tx[c].astype(bool)
    if "voided" in tx.columns:
        tx["voided"] = tx["voided"].fillna(False).astype(bool)
    cust = pd.read_sql("SELECT customer_id, open_day FROM customers", eng)
    return cust, tx


def enrich(log=print, from_db: bool = False) -> dict:
    from app.ml.pipeline import _write  # bulk loader (COPY on PostgreSQL)

    t0 = time.time()
    wait_ready(log=log)
    init_db()
    cust, tx = _base_from_db(log) if from_db else _base_from_manifest(log)
    out = layer.build(tx, cust, log=log)
    eng = get_engine()
    for name, df in out.items():
        t1 = time.time()
        log(f"  writing {name} ({len(df):,} rows) ...")
        _write(df, name)
        log(f"    done in {time.time() - t1:.0f}s")
    with eng.begin() as c:
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_tx_cust ON transactions(customer_id, posted_ts)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_tx_id ON transactions(id)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_tx_acct ON transactions(account_id)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_val_hold ON holding_valuations(holding_id, month)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_bud ON budgets(customer_id, month)"))
    summary = {k: int(len(v)) for k, v in out.items()}
    kv_set("finance_layer", {"built_at": int(time.time()), "tables": summary, "seed": layer.SEED})
    log(f"finance layer written in {time.time() - t0:.0f}s: {summary}")
    return summary


if __name__ == "__main__":
    enrich(from_db="--from-db" in sys.argv)
