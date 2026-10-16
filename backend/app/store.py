"""In-memory read cache over the configured database (loaded at startup, reloaded after jobs)."""
from __future__ import annotations

import threading
from functools import lru_cache

import pandas as pd
from sqlalchemy import inspect

from app.db import ART, get_engine, kv_get

RES = ART / "results"


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.ready = False
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
        with self.lock:
            self.tx = tx
            self.customers = pd.read_sql("SELECT * FROM customers", eng)
            self.scores = pd.read_sql("SELECT * FROM fraud_scores", eng)
            self.labels = pd.read_sql("SELECT id, label FROM fraud_labels", eng)
            self.run = run
            self.clusters = kv_get("latest_clusters") or {"status": "not_run", "clusters": [], "assignments": []}
            self.manifest = kv_get("dataset_manifest") or {}
            self.by_cust = {k: g for k, g in self.tx.groupby("customer_id")}
            self._overview = None
            self.ready = True

    def add_transaction(self, row: dict) -> None:
        with self.lock:
            self.tx = pd.concat([self.tx, pd.DataFrame([row])], ignore_index=True)
            cid = row["customer_id"]
            self.by_cust[cid] = self.tx[self.tx.customer_id == cid]
            self._overview = None


@lru_cache
def get_store() -> Store:
    return Store()


def reload_store() -> None:
    get_store().load()
