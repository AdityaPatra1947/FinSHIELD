"""In-memory read cache over the configured database (loaded at startup, reloaded after jobs)."""
from __future__ import annotations

import threading
from functools import lru_cache

import pandas as pd
from sqlalchemy import inspect

from app.db import ART, get_engine, kv_get

RES = ART / "results"
FIN_TABLES = ("accounts", "loans", "holdings", "holding_valuations", "recurring_items", "budgets", "goals",
              "customer_profile", "income_brackets", "categories", "merchants", "income_types")


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.ready = False
        self.fin: dict | None = None
        self.load()

    def load(self) -> None:
        eng = get_engine()
        names = set(inspect(eng).get_table_names())
        run = kv_get("latest_run") if "results" in names else None
        if not {"transactions", "customers", "fraud_scores", "fraud_labels"} <= names or not run:
            self.ready = False
            return
        tx = pd.read_sql("SELECT * FROM transactions", eng)
        for c in ("eligible", "is_derived"):
            tx[c] = tx[c].astype(bool)
        if "voided" in tx.columns:
            tx["voided"] = tx["voided"].fillna(False).astype(bool)
        if "is_recurring" in tx.columns:
            tx["is_recurring"] = tx["is_recurring"].fillna(False).astype(bool)
        fin = self._load_fin(eng, names)
        with self.lock:
            self.tx = tx
            self.customers = pd.read_sql("SELECT * FROM customers", eng)
            self.scores = pd.read_sql("SELECT * FROM fraud_scores", eng)
            self.labels = pd.read_sql("SELECT id, label FROM fraud_labels", eng)
            self.run = run
            self.clusters = kv_get("latest_clusters") or {"status": "not_run", "clusters": [], "assignments": []}
            self.manifest = kv_get("dataset_manifest") or {}
            self.by_cust = {k: g for k, g in self.tx.groupby("customer_id")}
            self.fin = fin
            self._overview = None
            self.ready = True

    @staticmethod
    def _load_fin(eng, names) -> dict | None:
        if not set(FIN_TABLES) <= names or "txn_type" not in pd.read_sql("SELECT * FROM transactions LIMIT 1", eng).columns:
            return None
        rd = lambda t: pd.read_sql(f"SELECT * FROM {t}", eng)
        holdings = rd("holdings")
        holdings["tax_80c"] = holdings["tax_80c"].astype(bool)
        frames = {"accounts": rd("accounts"), "loans": rd("loans"), "holdings": holdings,
                  "vals": rd("holding_valuations"), "rec": rd("recurring_items"), "budgets": rd("budgets"), "goals": rd("goals")}
        fin: dict = {"_empty": {k: v.head(0) for k, v in frames.items()}}
        for k, df in frames.items():
            fin[k] = {cid: g for cid, g in df.groupby("customer_id")}
        prof = rd("customer_profile")
        fin["profile"] = {int(r["customer_id"]): r for r in prof.to_dict("records")}
        fin["brackets"] = rd("income_brackets")
        fin["categories"] = rd("categories")
        fin["merchants"] = rd("merchants")
        fin["income_types"] = rd("income_types")
        fin["_frames"] = frames
        return fin

    def refresh_fin_group(self, name: str, df: pd.DataFrame) -> None:
        """Replace one finance table in memory (after a write) and regroup it by customer."""
        if self.fin is None:
            return
        with self.lock:
            self.fin["_frames"][name] = df
            self.fin[name] = {cid: g for cid, g in df.groupby("customer_id")}

    def add_transaction(self, row: dict) -> None:
        with self.lock:
            self.tx = pd.concat([self.tx, pd.DataFrame([row])], ignore_index=True)
            cid = row["customer_id"]
            self.by_cust[cid] = self.tx[self.tx.customer_id == cid]
            self._overview = None

    def update_transaction(self, txn_id: int, **cols) -> None:
        with self.lock:
            m = self.tx.id == txn_id
            if not m.any():
                return
            for k, v in cols.items():
                self.tx.loc[m, k] = v
            cid = int(self.tx.loc[m, "customer_id"].iloc[0])
            self.by_cust[cid] = self.tx[self.tx.customer_id == cid]
            self._overview = None


@lru_cache
def get_store() -> Store:
    return Store()


def reload_store() -> None:
    get_store().load()
