"""Administration: users, audit log, jobs (retrain / recluster / regenerate), model promotion, org overview."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import uuid
from typing import Literal

import joblib
import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.security import hash_password, random_password
from app.db import ART, get_engine, now
from app.deps import CurrentUser, admin_only, audit, err, require
from app.ml.features import ALLOWLIST, FEATURE_VERSION
from app.ml.generator import ORIGIN_TS
from app.ml.train import FAMILIES
from app.services.spending import CREDITS, GROSS, INCOME
from app.store import Store, get_store, reload_store

router = APIRouter()
BACKEND = ART.parent


# ------------------------------------------------------------------ users
class NewUser(BaseModel):
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    role: Literal["customer", "analyst", "admin"]
    customer_id: int | None = None


class UserPatch(BaseModel):
    active: bool | None = None
    reset_password: bool = False


@router.get("/admin/users")
def list_users(user: CurrentUser = Depends(admin_only)):
    with get_engine().connect() as c:
        rows = c.execute(text("SELECT id,email,role,customer_id,active,created_at,last_login_at FROM users ORDER BY created_at")).fetchall()
    return {"items": [dict(id=r[0], email=r[1], role=r[2], customer_id=r[3], active=bool(r[4]), created_at=r[5],
                           last_login_at=r[6]) for r in rows]}


@router.post("/admin/users", status_code=201)
def create_user(body: NewUser, user: CurrentUser = Depends(admin_only)):
    if body.role == "customer" and body.customer_id is None:
        raise err(422, "customer_required", "Customer users need a customer_id", customer_id="required")
    s = get_store()
    if body.customer_id is not None and s.ready and body.customer_id not in s.by_cust:
        raise err(404, "not_found", "Customer not found")
    pw, uid = random_password(), str(uuid.uuid4())
    try:
        with get_engine().begin() as c:
            c.execute(text("INSERT INTO users(id,email,password_hash,role,customer_id,active,created_at) VALUES(:i,:e,:p,:r,:c,:a,:t)"),
                      {"i": uid, "e": body.email.strip().lower(), "p": hash_password(pw), "r": body.role,
                       "c": body.customer_id if body.role == "customer" else None, "a": True, "t": now()})
    except Exception:
        raise err(409, "email_exists", "A user with this email already exists")
    audit(user, "user_created", "user", uid, {"role": body.role, "email": body.email})
    return {"id": uid, "email": body.email, "role": body.role, "initial_password": pw,
            "note": "Shown once. The user should change it; only a hash is stored."}


@router.patch("/admin/users/{uid}")
def patch_user(uid: str, body: UserPatch, user: CurrentUser = Depends(admin_only)):
    out: dict = {"id": uid}
    with get_engine().begin() as c:
        if not c.execute(text("SELECT 1 FROM users WHERE id=:i"), {"i": uid}).fetchone():
            raise err(404, "not_found", "Resource unavailable")
        if body.active is not None:
            if uid == user.id and not body.active:
                raise err(409, "self_lockout", "You cannot deactivate your own account")
            c.execute(text("UPDATE users SET active=:a WHERE id=:i"), {"a": body.active, "i": uid})
            if not body.active:
                c.execute(text("UPDATE sessions SET revoked_at=:t WHERE user_id=:i AND revoked_at IS NULL"), {"t": now(), "i": uid})
            out["active"] = body.active
        if body.reset_password:
            pw = random_password()
            c.execute(text("UPDATE users SET password_hash=:p WHERE id=:i"), {"p": hash_password(pw), "i": uid})
            c.execute(text("UPDATE sessions SET revoked_at=:t WHERE user_id=:i AND revoked_at IS NULL"), {"t": now(), "i": uid})
            out["new_password"] = pw
    audit(user, "user_updated", "user", uid, {"active": body.active, "password_reset": body.reset_password})
    return out


@router.get("/admin/audit")
def audit_log(limit: int = Query(100, le=500), user: CurrentUser = Depends(admin_only)):
    with get_engine().connect() as c:
        rows = c.execute(text("SELECT id,actor_email,action,object_type,object_id,safe_details,occurred_at FROM audit_events "
                              "ORDER BY id DESC LIMIT :n"), {"n": limit}).fetchall()
    return {"items": [dict(id=r[0], actor=r[1], action=r[2], object_type=r[3], object_id=r[4],
                           details=json.loads(r[5] or "{}"), occurred_at=r[6]) for r in rows]}


# ------------------------------------------------------------------ jobs
class JobBody(BaseModel):
    kind: Literal["train", "cluster", "regenerate"]
    confirm: bool = False


_job_lock = threading.Lock()
STAGE = {"train": "train", "cluster": "cluster", "regenerate": "all"}


def _run_job(job_id: str, kind: str) -> None:
    eng = get_engine()
    with eng.begin() as c:
        c.execute(text("UPDATE jobs SET status='running', started_at=:t WHERE id=:i"), {"t": now(), "i": job_id})
    tail: list[str] = []
    code = 1
    try:
        p = subprocess.Popen([sys.executable, "-u", "-m", "app.ml.pipeline", STAGE[kind]], cwd=BACKEND,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:  # type: ignore[union-attr]
            tail = (tail + [line.rstrip()])[-40:]
            with eng.begin() as c:
                c.execute(text("UPDATE jobs SET log_tail=:l WHERE id=:i"), {"l": "\n".join(tail)[-4000:], "i": job_id})
        code = p.wait()
    except Exception:
        tail.append("job runner error")
    status = "succeeded" if code == 0 else "failed"
    with eng.begin() as c:
        c.execute(text("UPDATE jobs SET status=:s, finished_at=:t, error_code=:e, log_tail=:l WHERE id=:i"),
                  {"s": status, "t": now(), "e": None if code == 0 else f"exit_{code}", "l": "\n".join(tail)[-4000:], "i": job_id})
    if code == 0:
        reload_store()
    with _job_lock:
        pass


@router.post("/admin/jobs", status_code=202)
def start_job(body: JobBody, user: CurrentUser = Depends(admin_only)):
    if body.kind == "regenerate" and not body.confirm:
        raise err(422, "confirmation_required", "Regenerating replaces the dataset and discards manually entered transactions; set confirm=true")
    eng = get_engine()
    with _job_lock, eng.begin() as c:
        if c.execute(text("SELECT 1 FROM jobs WHERE status IN ('pending','running')")).fetchone():
            raise err(409, "job_active", "Another job is already running (one active run per organization)")
        jid = str(uuid.uuid4())
        c.execute(text("INSERT INTO jobs(id,kind,status,payload,requested_by,created_at) VALUES(:i,:k,'pending',:p,:u,:t)"),
                  {"i": jid, "k": body.kind, "p": "{}", "u": user.id, "t": now()})
    audit(user, f"job_{body.kind}_requested", "job", jid)
    threading.Thread(target=_run_job, args=(jid, body.kind), daemon=True).start()
    return {"id": jid, "status": "pending"}


@router.get("/admin/jobs")
def list_jobs(user: CurrentUser = Depends(admin_only)):
    with get_engine().connect() as c:
        rows = c.execute(text("SELECT id,kind,status,created_at,started_at,finished_at,log_tail,error_code FROM jobs "
                              "ORDER BY created_at DESC LIMIT 20")).fetchall()
    return {"items": [dict(id=r[0], kind=r[1], status=r[2], created_at=r[3], started_at=r[4], finished_at=r[5],
                           log_tail=r[6], error_code=r[7]) for r in rows]}


# ------------------------------------------------------------------ promotion / rollback
class PromoteBody(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    expected_current: str | None = None


def _history():
    with get_engine().connect() as c:
        return c.execute(text("SELECT id,family,run_id,artifact_sha256,reason,kind,actor_id,created_at FROM model_promotions "
                              "ORDER BY id DESC")).fetchall()


def _verify_artifact(family: str, run: dict) -> dict:
    m = next(x for x in run["models"] if x["family"] == family)
    path = ART / "models" / f"{family}.joblib"
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != m["artifact"]["sha256"]:
        raise err(409, "artifact_mismatch", "Artifact missing or checksum differs from the recorded run")
    bundle = joblib.load(path)  # trusted, internally produced artifact only
    if bundle.get("feature_version") != FEATURE_VERSION or bundle.get("allowlist") != ALLOWLIST or bundle.get("family") != family:
        raise err(409, "feature_incompatible", "Artifact feature contract does not match the application")
    return m


@router.get("/ml/promotions")
def promotions(user: CurrentUser = Depends(require("analyst", "admin"))):
    return {"items": [dict(id=r[0], family=r[1], run_id=r[2], artifact_sha256=r[3], reason=r[4], kind=r[5],
                           actor_id=r[6], created_at=r[7]) for r in _history()]}


@router.post("/ml/models/{family}/promote")
def promote(family: str, body: PromoteBody, user: CurrentUser = Depends(admin_only), s: Store = Depends(get_store)):
    if family not in FAMILIES:
        raise err(404, "not_found", "Unknown model family")
    hist = _history()
    cur = hist[0][1] if hist else None
    if body.expected_current != cur:
        raise err(409, "stale_current", f"Current promoted model is {cur!r}; refresh and retry")
    m = _verify_artifact(family, s.run)
    if m["threshold"] is None:
        raise err(409, "no_feasible_threshold", "This model has no operational threshold (constraints unmet); promotion blocked")
    with get_engine().begin() as c:
        c.execute(text("INSERT INTO model_promotions(family,run_id,artifact_sha256,reason,kind,actor_id,created_at) "
                       "VALUES(:f,:r,:a,:why,'promote',:u,:t)"),
                  {"f": family, "r": s.run["run_id"], "a": m["artifact"]["sha256"], "why": body.reason, "u": user.id, "t": now()})
    audit(user, "model_promoted", "model", family, {"reason": body.reason, "previous": cur})
    return {"promoted": family}


@router.post("/ml/models/rollback")
def rollback(body: PromoteBody, user: CurrentUser = Depends(admin_only), s: Store = Depends(get_store)):
    hist = _history()
    prev = next((r for r in hist[1:] if r[1] != (hist[0][1] if hist else None)), None)
    if not hist or prev is None:
        raise err(409, "no_previous", "No earlier promoted version to roll back to")
    _verify_artifact(prev[1], s.run)
    with get_engine().begin() as c:
        c.execute(text("INSERT INTO model_promotions(family,run_id,artifact_sha256,reason,kind,actor_id,created_at) "
                       "VALUES(:f,:r,:a,:why,'rollback',:u,:t)"),
                  {"f": prev[1], "r": prev[2], "a": prev[3], "why": body.reason, "u": user.id, "t": now()})
    audit(user, "model_rolled_back", "model", prev[1], {"reason": body.reason, "from": hist[0][1]})
    return {"active": prev[1]}


# ------------------------------------------------------------------ org overview (all visualisations feed)
def _month(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, unit="s", utc=True).dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m")


@router.get("/admin/overview")
def overview(user: CurrentUser = Depends(require("analyst", "admin")), s: Store = Depends(get_store)):
    if not s.ready:
        raise err(503, "not_built", "Dataset/models not built yet")
    cached = getattr(s, "_overview", None)
    if cached is not None:
        return {**cached, **_live_parts()}
    out = _compute_overview(s)
    s._overview = out
    return {**out, **_live_parts()}


def warm() -> None:
    """Precompute the org overview in the background so the first admin visit is fast."""
    s = get_store()
    if s.ready and getattr(s, "_overview", None) is None:
        s._overview = _compute_overview(s)


def _live_parts() -> dict:
    """Parts that change without a data reload: alert triage, promotion pointer, user counts."""
    with get_engine().connect() as c:
        states = dict(c.execute(text("SELECT state, COUNT(*) FROM alert_state GROUP BY state")).fetchall())
        prom = c.execute(text("SELECT family FROM model_promotions ORDER BY id DESC LIMIT 1")).fetchone()
        roles = dict(c.execute(text("SELECT role, COUNT(*) FROM users GROUP BY role")).fetchall())
    return {"alert_states": {k: int(v) for k, v in states.items()}, "promoted_family": prom[0] if prom else None,
            "users_by_role": {k: int(v) for k, v in roles.items()}}


def _compute_overview(s: Store) -> dict:
    tx = s.tx
    posted = tx[tx.status == "posted"].copy()
    posted["month"] = _month(posted.posted_ts)
    g = posted[posted.purpose.isin(GROSS)].groupby("month").amount_minor.sum()
    cr = posted[posted.purpose.isin(CREDITS)].groupby("month").amount_minor.sum()
    inc = posted[posted.purpose.isin(INCOME)].groupby("month").amount_minor.sum()
    months = sorted(posted.month.unique())
    monthly = [{"bucket": m, "net_spending_minor": str(int(g.get(m, 0) - cr.get(m, 0))),
                "recognized_income_minor": str(int(inc.get(m, 0)))} for m in months]
    el = tx[tx.eligible & (tx.status == "posted")].copy()
    el["month"] = _month(el.ts)
    fm = el.groupby("month").fraud.agg(["sum", "count"])
    fraud_monthly = [{"bucket": m, "fraud": int(fm.at[m, "sum"]), "decisions": int(fm.at[m, "count"])} for m in fm.index]
    fch = el.groupby("channel").fraud.agg(["sum", "count"])
    cat = posted[posted.purpose.isin(GROSS)].groupby(posted.category.fillna("uncategorized")).amount_minor.sum().sort_values(ascending=False)
    cl = s.clusters.get("clusters", [])
    return {
        "totals": {"customers": int(len(s.customers)), "transactions": int(len(tx)),
                   "eligible_decisions": int(len(el)), "fraud_labeled": int(el.fraud.sum()),
                   "scored_decisions": int(len(s.scores))},
        "monthly": monthly, "fraud_monthly": fraud_monthly,
        "fraud_by_channel": [{"channel": k, "fraud": int(r["sum"]), "decisions": int(r["count"])} for k, r in fch.iterrows()],
        "categories": [{"category": k, "gross_minor": str(int(v))} for k, v in cat.items()],
        "purpose_counts": {k: int(v) for k, v in tx.purpose.value_counts().items()},
        "cluster_sizes": [{"cluster_id": k["cluster_id"], "name": k["name"], "size": k["size"]} for k in cl],
        "model_summary": [{"family": m["family"], "label": m["label"], "ap": m["test"].get("average_precision"),
                           "threshold_status": m["threshold_status"]} for m in s.run["models"]],
        "champion": s.run.get("champion"), "origin_ts": ORIGIN_TS,
    }
