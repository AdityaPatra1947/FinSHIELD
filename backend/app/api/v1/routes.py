"""Data API. Every route requires a session; roles and customer ownership are enforced server-side."""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_engine, now
from app.deps import CurrentUser, audit, authorize_customer, current_user, err, staff
from app.ml.generator import DAY, ORIGIN_TS
from app.services import spending
from app.store import RES, Store, get_store

router = APIRouter()
TZ = "Asia/Kolkata"
_insert_lock = threading.Lock()
MAX_MINOR = 1_000_000_000 * 100


def store() -> Store:
    s = get_store()
    if not s.ready:
        raise err(503, "not_built", "Dataset/models not built yet. Run `python -m app.ml.pipeline`.")
    return s


def active_family() -> str | None:
    with get_engine().connect() as c:
        row = c.execute(text("SELECT family FROM model_promotions ORDER BY id DESC LIMIT 1")).fetchone()
    return row[0] if row else None


def _local(ts: float) -> str:
    return datetime.fromtimestamp(ts, ZoneInfo(TZ)).isoformat()


def _mask(cid: int) -> str:
    return f"CUST-{cid:04d}"


def default_period() -> tuple[int, int]:
    """Last 12 calendar months through the end of the current month (Asia/Kolkata), half-open."""
    n = datetime.now(ZoneInfo(TZ))
    end = (n.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)
    m = end.year * 12 + end.month - 1 - 12
    start = end.replace(year=m // 12, month=m % 12 + 1)
    return int(start.timestamp()), int(end.timestamp())


def _ts(d: str | None, default: int) -> int:
    if not d:
        return default
    try:
        return int(datetime.fromisoformat(d).replace(tzinfo=ZoneInfo(TZ)).timestamp())
    except ValueError:
        raise err(422, "invalid_date", "Dates must be ISO format YYYY-MM-DD")


def _cust_tx(s: Store, user: CurrentUser, cid: int) -> pd.DataFrame:
    authorize_customer(user, cid)
    if cid not in s.by_cust:
        raise err(404, "not_found", "Resource unavailable")
    return s.by_cust[cid]


# ------------------------------------------------------------------ customers
@router.get("/customers")
def customers(q: str | None = None, page: int = 1, size: int = Query(25, le=200),
              user: CurrentUser = Depends(staff), s: Store = Depends(store)):
    c = s.customers
    if q:
        c = c[c.display_name.str.contains(q, case=False) | c.customer_id.astype(str).eq(q)]
    seg = {a["customer_id"]: a["cluster_id"] for a in s.clusters.get("assignments", [])}
    names = {k["cluster_id"]: k["name"] for k in s.clusters.get("clusters", [])}
    return {"total": int(len(c)), "page": page, "items": [
        {"customer_id": int(r.customer_id), "name": r.display_name, "masked": _mask(int(r.customer_id)),
         "cluster_id": seg.get(int(r.customer_id)), "cluster_name": names.get(seg.get(int(r.customer_id))),
         "synthetic": True} for r in c.iloc[(page - 1) * size: page * size].itertuples()]}


@router.get("/customers/{cid}/cluster")
def customer_cluster(cid: int, user: CurrentUser = Depends(current_user), s: Store = Depends(store)):
    authorize_customer(user, cid)
    for a in s.clusters.get("assignments", []):
        if a["customer_id"] == cid:
            name = next(k["name"] for k in s.clusters["clusters"] if k["cluster_id"] == a["cluster_id"])
            return {"status": "assigned", "cluster_id": a["cluster_id"], "cluster_name": name,
                    "as_of_ts": s.clusters["as_of_ts"], "run_note": "Cluster IDs are meaningful only within this run."}
    return {"status": "insufficient_history", "cluster_id": None}


# ------------------------------------------------------------------ reports
@router.get("/reports/spending")
def report_spending(customer_id: int, start: str | None = None, end: str | None = None,
                    user: CurrentUser = Depends(current_user), s: Store = Depends(store)):
    tx = _cust_tx(s, user, customer_id)
    d0, d1 = default_period()
    a, b = _ts(start, d0), _ts(end, d1)
    if b <= a:
        raise err(422, "invalid_period", "end must be after start")
    if b - a > 366 * DAY:
        raise err(422, "interval_too_long", "Max interactive interval is 366 days")
    tot = spending.spending_totals(tx, a, b)
    prev = spending.spending_totals(tx, a - (b - a), a)
    pn, cn = int(prev["net_spending_minor"]), int(tot["net_spending_minor"])
    return {**tot, "timezone": TZ, "period": {"start": _local(a), "end": _local(b), "half_open": True},
            "net_change_vs_prior_period_percent": (100.0 * (cn - pn) / abs(pn)) if pn else None,
            "net_change_reason": None if pn else "prior period net spending is zero",
            "categories": spending.category_breakdown(tx, a, b), "cash": spending.cash_reconciliation(tx),
            "coverage_status": "synthetic_complete"}


@router.get("/reports/trends")
def report_trends(customer_id: int, start: str | None = None, end: str | None = None,
                  user: CurrentUser = Depends(current_user), s: Store = Depends(store)):
    tx = _cust_tx(s, user, customer_id)
    d0, d1 = default_period()
    a, b = _ts(start, d0), _ts(end, d1)
    if b - a > 366 * DAY or b <= a:
        raise err(422, "invalid_period", "Period must be positive and at most 366 days")
    return {"bucket": "month", "timezone": TZ, "items": spending.monthly_trend(tx, a, b)}


# ------------------------------------------------------------------ transactions
@router.get("/transactions")
def transactions(customer_id: int, status: str | None = None, purpose: str | None = None,
                 cursor: int | None = None, limit: int = Query(50, le=200),
                 user: CurrentUser = Depends(current_user), s: Store = Depends(store)):
    t = _cust_tx(s, user, customer_id)
    if status:
        t = t[t.status == status]
    if purpose:
        t = t[t.purpose == purpose]
    t = t.sort_values(["ts", "id"], ascending=False)
    if cursor is not None:
        t = t[t.id < cursor]
    page = t.head(limit)
    fam = active_family()
    sc = s.scores.set_index("txn_id")
    items = []
    for r in page.itertuples():
        p = float(sc.at[r.id, fam]) if fam and r.id in sc.index else None
        items.append({"id": int(r.id), "occurred_at": _local(r.ts), "amount_minor": str(int(r.amount_minor)),
                      "currency": "INR", "direction": r.direction, "status": r.status, "purpose": r.purpose,
                      "category": r.category if isinstance(r.category, str) else None, "channel": r.channel,
                      "account_kind": r.account_kind, "fraud_probability": p})
    return {"items": items, "next_cursor": int(page.id.min()) if len(t) > limit else None}


CATEGORIES = ["groceries", "dining", "transport", "shopping", "entertainment", "health", "utilities", "travel",
              "education", "rent", "fees"]


class ManualTx(BaseModel):
    account_kind: Literal["bank", "cash", "credit_card"] = "bank"
    amount: str = Field(max_length=20)  # decimal INR string; at most 2 dp
    purpose: Literal["purchase", "fee", "salary"] = "purchase"
    category: str | None = None
    merchant_display: str | None = Field(default=None, max_length=80)
    occurred_at: datetime


@router.post("/transactions", status_code=201)
def create_transaction(body: ManualTx, user: CurrentUser = Depends(current_user), s: Store = Depends(store),
                       idempotency_key: str | None = Header(default=None, max_length=80)):
    if user.role != "customer" or user.customer_id is None:
        raise err(403, "forbidden", "Only customers can enter their own transactions")
    try:
        amt = Decimal(body.amount)
    except InvalidOperation:
        raise err(422, "invalid_amount", "Amount must be a decimal number", amount="invalid")
    if amt <= 0 or amt.as_tuple().exponent < -2 or not amt.is_finite():
        raise err(422, "invalid_amount", "Amount must be positive with at most two decimal places", amount="invalid")
    minor = int(amt * 100)
    if minor > MAX_MINOR:
        raise err(422, "amount_too_large", "Amount exceeds the per-transaction limit")
    if body.occurred_at.tzinfo is None:
        raise err(422, "timezone_required", "occurred_at must include a UTC offset", occurred_at="offset required")
    ts = int(body.occurred_at.timestamp())
    if ts > now() + 300 or ts < ORIGIN_TS:
        raise err(422, "invalid_date", "Date must be within the data range and not in the future")
    if body.purpose == "purchase" and body.category not in CATEGORIES:
        raise err(422, "invalid_category", "Pick a valid category", category="invalid")
    cat = body.category if body.purpose == "purchase" else ("fees" if body.purpose == "fee" else None)
    direction = "credit" if body.purpose == "salary" else "debit"
    body_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    eng = get_engine()
    if idempotency_key:
        with eng.connect() as c:
            row = c.execute(text("SELECT body_hash,response_status,response_body FROM idempotency_keys "
                                 "WHERE user_id=:u AND route='POST /transactions' AND key=:k"),
                            {"u": user.id, "k": idempotency_key}).fetchone()
        if row:
            if row[0] != body_hash:
                raise err(409, "idempotency_conflict", "Idempotency key reused with a different body")
            return json.loads(row[2])
    with _insert_lock, eng.begin() as c:
        new_id = int(c.execute(text("SELECT COALESCE(MAX(id),0)+1 FROM transactions")).scalar())
        day = int((ts - ORIGIN_TS) // DAY + 1)
        row = dict(id=new_id, customer_id=user.customer_id, account_kind=body.account_kind, amount_minor=minor,
                   direction=direction, status="posted", purpose=body.purpose, category=cat,
                   merchant_key=(body.merchant_display or None), channel="manual", ts=ts, device_token=None,
                   payee_token=None, eligible=False, fraud=0, linked_id=None, day=day, posted_ts=float(ts),
                   is_derived=False)
        c.execute(text("INSERT INTO transactions(" + ",".join(row) + ") VALUES(" + ",".join(f":{k}" for k in row) + ")"), row)
        resp = {"id": new_id, "amount_minor": str(minor), "status": "posted", "purpose": body.purpose,
                "category": cat, "occurred_at": _local(ts)}
        if idempotency_key:
            c.execute(text("INSERT INTO idempotency_keys(user_id,route,key,body_hash,response_status,response_body,created_at) "
                           "VALUES(:u,'POST /transactions',:k,:h,201,:b,:t)"),
                      {"u": user.id, "k": idempotency_key, "h": body_hash, "b": json.dumps(resp), "t": now()})
    s.add_transaction(row)
    audit(user, "transaction_created", "transaction", str(new_id), {"purpose": body.purpose, "amount_minor": minor})
    return resp


@router.get("/transactions/{txn_id}/fraud")
def txn_fraud(txn_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(store)):
    row = s.tx[s.tx.id == txn_id]
    if row.empty:
        raise err(404, "not_found", "Resource unavailable")
    authorize_customer(user, int(row.iloc[0].customer_id))
    fam = active_family()
    sc = s.scores[s.scores.txn_id == txn_id]
    if not fam or sc.empty:
        return {"available": False, "reason": "not scored (outside scored period, ineligible, or no promoted model)"}
    thr = next(m["threshold"] for m in s.run["models"] if m["family"] == fam)
    p = float(sc.iloc[0][fam])
    return {"available": True, "model": fam, "probability": p, "flagged_for_review": thr is not None and p >= thr,
            "reasons": json.loads(sc.iloc[0].reasons),
            "note": "Contextual signals, not proof of fraud."}


# ------------------------------------------------------------------ fraud review (staff)
@router.get("/fraud/alerts")
def alerts(page: int = 1, size: int = Query(25, le=200), user: CurrentUser = Depends(staff), s: Store = Depends(store)):
    fam = active_family()
    if fam is None:
        return {"available": False, "items": [],
                "reason": "No promoted model. An administrator must promote a feasible model; nothing is auto-deployed."}
    thr = next(m["threshold"] for m in s.run["models"] if m["family"] == fam)
    if thr is None:
        return {"available": False, "items": [], "reason": "Promoted model has no operational threshold."}
    sc = s.scores[s.scores[fam] >= thr].sort_values(fam, ascending=False)
    with get_engine().connect() as c:
        states = {r[0]: (r[1], r[2]) for r in c.execute(text("SELECT txn_id,state,note FROM alert_state"))}
    tx = s.tx.set_index("id")
    lab = s.labels.set_index("id").label
    items = []
    for r in sc.iloc[(page - 1) * size: page * size].itertuples():
        t = tx.loc[r.txn_id]
        st = states.get(int(r.txn_id), ("open", None))
        items.append({"txn_id": int(r.txn_id), "customer": _mask(int(t.customer_id)), "customer_id": int(t.customer_id),
                      "amount_minor": str(int(t.amount_minor)), "purpose": t.purpose, "channel": t.channel,
                      "occurred_at": _local(int(t.ts)), "probability": float(getattr(r, fam)), "threshold": thr,
                      "reasons": json.loads(r.reasons), "state": st[0], "note": st[1],
                      "synthetic_label": int(lab.get(int(r.txn_id), -1))})
    return {"available": True, "model": fam, "threshold": thr, "total": int(len(sc)), "items": items,
            "note": "Scores are estimates for review, not proof of fraud. Synthetic label shown for demo only."}


class AlertPatch(BaseModel):
    state: Literal["open", "in_review", "resolved"]
    note: str | None = Field(default=None, max_length=500)


@router.patch("/fraud/alerts/{txn_id}")
def patch_alert(txn_id: int, body: AlertPatch, user: CurrentUser = Depends(staff)):
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM alert_state WHERE txn_id=:i"), {"i": txn_id})
        c.execute(text("INSERT INTO alert_state(txn_id,state,note,updated_by,updated_at) VALUES(:i,:s,:n,:u,:t)"),
                  {"i": txn_id, "s": body.state, "n": body.note, "u": user.id, "t": now()})
    audit(user, "alert_state_changed", "transaction", str(txn_id), {"state": body.state})
    return {"txn_id": txn_id, "state": body.state}


# ------------------------------------------------------------------ ML insights (staff)
@router.get("/dataset")
def dataset(user: CurrentUser = Depends(staff), s: Store = Depends(store)):
    return s.manifest


@router.get("/ml/comparison")
def comparison(user: CurrentUser = Depends(staff), s: Store = Depends(store)):
    return {**s.run, "promoted_family": active_family()}


@router.get("/ml/metrics.csv")
def metrics_csv(user: CurrentUser = Depends(staff)):
    return FileResponse(RES / "metrics.csv", media_type="text/csv", filename="finshield_metrics.csv")


@router.get("/ml/model-card")
def model_card(user: CurrentUser = Depends(staff)):
    return PlainTextResponse((RES / "model_card.md").read_text(), media_type="text/markdown")


@router.get("/clusters/latest")
def clusters(user: CurrentUser = Depends(staff), s: Store = Depends(store)):
    c = dict(s.clusters)
    c.pop("statuses", None)
    return c
