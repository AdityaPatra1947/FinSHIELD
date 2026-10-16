"""First-run setup: schema, fixed local demo users, initial audited model promotion.

The demo accounts below use deliberately simple passwords for a local, synthetic-data demo.
Change or deactivate them (Admin > Users) before exposing the app anywhere.
"""
from __future__ import annotations

import uuid
from getpass import getpass

from sqlalchemy import text

from app.core.config import ensure_dev_pepper
from app.core.security import hash_password
from app.db import ART, get_engine, init_db, kv_get, now

CRED_FILE = ART / "demo_credentials.txt"

# (email, password, role, customer_id, previous demo email to migrate from)
DEMO_USERS = [
    ("admin@gmail.com", "admin123", "admin", None, "admin@finshield.local"),
    ("analyst@gmail.com", "analyst123", "analyst", None, "analyst@finshield.local"),
    ("customer1@gmail.com", "customer123", "customer", 1, "customer0001@finshield.local"),
    ("customer2@gmail.com", "customer123", "customer", 2, "customer0002@finshield.local"),
    ("customer3@gmail.com", "customer123", "customer", 3, "customer0003@finshield.local"),
]


def _insert(c, email, role, pw, customer_id=None) -> str:
    uid = str(uuid.uuid4())
    c.execute(text("INSERT INTO users(id,email,password_hash,role,customer_id,active,created_at) VALUES(:i,:e,:p,:r,:c,:a,:t)"),
              {"i": uid, "e": email, "p": hash_password(pw), "r": role, "c": customer_id, "a": True, "t": now()})
    return uid


def seed_users() -> list[str]:
    """Idempotently ensure the demo accounts exist with the documented credentials (hashed in the DB)."""
    ensure_dev_pepper()
    init_db()
    lines, admin_id = [], None
    with get_engine().begin() as c:
        for email, pw, role, cid, old in DEMO_USERS:
            row = c.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email}).fetchone() \
                or c.execute(text("SELECT id FROM users WHERE email=:e"), {"e": old}).fetchone()
            if row:
                uid = row[0]
                c.execute(text("UPDATE users SET email=:e, password_hash=:p, role=:r, customer_id=:c, active=:a WHERE id=:i"),
                          {"e": email, "p": hash_password(pw), "r": role, "c": cid, "a": True, "i": uid})
                c.execute(text("UPDATE sessions SET revoked_at=:t WHERE user_id=:i AND revoked_at IS NULL"), {"t": now(), "i": uid})
            else:
                uid = _insert(c, email, role, pw, cid)
            if role == "admin":
                admin_id = uid
            lines.append(f"{role:9s} {email:24s} {pw}" + (f"   (customer {cid})" if cid else ""))
    ART.mkdir(exist_ok=True)
    CRED_FILE.write_text("FinShield local demo credentials (synthetic data; simple passwords for local use only)\n" +
                         "\n".join(lines) + "\n")
    _bootstrap_promotion(admin_id)
    return lines


def _bootstrap_promotion(admin_id: str | None) -> None:
    run = kv_get("latest_run")
    if not run or not run.get("champion"):
        return
    with get_engine().begin() as c:
        if c.execute(text("SELECT 1 FROM model_promotions")).fetchone():
            return
        m = next(x for x in run["models"] if x["family"] == run["champion"])
        c.execute(text("INSERT INTO model_promotions(family,run_id,artifact_sha256,reason,kind,actor_id,created_at) "
                       "VALUES(:f,:r,:a,:w,'promote',:u,:t)"),
                  {"f": run["champion"], "r": run["run_id"], "a": m["artifact"]["sha256"],
                   "w": "Initial setup: promoted frozen champion (setup script, admin-initiated)", "u": admin_id, "t": now()})


def bootstrap_admin() -> None:
    ensure_dev_pepper()
    init_db()
    email = input("Admin email: ").strip().lower()
    pw = getpass("Password (min 12 chars): ")
    if len(pw) < 12 or pw != getpass("Repeat password: "):
        raise SystemExit("Passwords must match and be at least 12 characters.")
    with get_engine().begin() as c:
        _insert(c, email, "admin", pw)
    print("Admin created.")
