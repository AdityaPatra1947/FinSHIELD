"""Database access. Uses DATABASE_URL (Neon/PostgreSQL via psycopg3) when set, else local SQLite."""
from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

from sqlalchemy import (BigInteger, Boolean, Column, Integer, MetaData, String, Table, Text, create_engine,
                        text)
from sqlalchemy.engine import Engine

from app.core.config import ConfigError, SAFE_SSL, _psycopg_url, get_settings

ART = Path(__file__).resolve().parents[2] / "artifacts"
SQLITE_PATH = ART / "finshield.db"

md = MetaData()
users = Table("users", md,
              Column("id", String(36), primary_key=True), Column("email", String(255), unique=True, nullable=False),
              Column("password_hash", Text, nullable=False), Column("role", String(16), nullable=False),
              Column("customer_id", Integer), Column("active", Boolean, nullable=False, default=True),
              Column("created_at", BigInteger, nullable=False), Column("last_login_at", BigInteger))
sessions = Table("sessions", md,
                 Column("id", String(36), primary_key=True), Column("user_id", String(36), nullable=False),
                 Column("token_hash", String(64), unique=True, nullable=False), Column("csrf_hash", String(64), nullable=False),
                 Column("created_at", BigInteger, nullable=False), Column("last_seen_at", BigInteger, nullable=False),
                 Column("idle_expires_at", BigInteger, nullable=False), Column("absolute_expires_at", BigInteger, nullable=False),
                 Column("revoked_at", BigInteger))
audit_events = Table("audit_events", md,
                     Column("id", Integer, primary_key=True, autoincrement=True), Column("actor_id", String(36)),
                     Column("actor_email", String(255)), Column("action", String(64), nullable=False),
                     Column("object_type", String(32)), Column("object_id", String(64)), Column("safe_details", Text),
                     Column("request_id", String(36)), Column("occurred_at", BigInteger, nullable=False))
jobs = Table("jobs", md,
             Column("id", String(36), primary_key=True), Column("kind", String(32), nullable=False),
             Column("status", String(16), nullable=False), Column("payload", Text), Column("requested_by", String(36)),
             Column("created_at", BigInteger, nullable=False), Column("started_at", BigInteger), Column("finished_at", BigInteger),
             Column("log_tail", Text), Column("error_code", String(64)))
results = Table("results", md, Column("key", String(64), primary_key=True), Column("value", Text, nullable=False),
                Column("updated_at", BigInteger, nullable=False))
model_promotions = Table("model_promotions", md,
                         Column("id", Integer, primary_key=True, autoincrement=True), Column("family", String(40), nullable=False),
                         Column("run_id", String(32)), Column("artifact_sha256", String(64)), Column("reason", Text),
                         Column("kind", String(16), nullable=False), Column("actor_id", String(36)),
                         Column("created_at", BigInteger, nullable=False))
alert_state = Table("alert_state", md, Column("txn_id", Integer, primary_key=True), Column("state", String(16)),
                    Column("note", Text), Column("updated_by", String(36)), Column("updated_at", BigInteger))
idempotency_keys = Table("idempotency_keys", md,
                         Column("user_id", String(36), primary_key=True), Column("route", String(64), primary_key=True),
                         Column("key", String(80), primary_key=True), Column("body_hash", String(64), nullable=False),
                         Column("response_status", Integer), Column("response_body", Text), Column("created_at", BigInteger))


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    if s.database_url:
        u = _psycopg_url(s.database_url)
        if u.query.get("sslmode") not in SAFE_SSL:
            raise ConfigError("tls_not_enforced: DATABASE_URL must include sslmode=require|verify-ca|verify-full")
        return create_engine(u, pool_size=s.pool_size, max_overflow=s.max_overflow, pool_pre_ping=True,
                             pool_recycle=300, connect_args={"connect_timeout": s.connect_timeout_s})
    ART.mkdir(exist_ok=True)
    return create_engine(f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False})


def backend_name() -> str:
    return "postgresql" if get_settings().database_url else "sqlite (local fallback)"


def init_db() -> None:
    md.create_all(get_engine())


def now() -> int:
    return int(time.time())


def kv_set(key: str, value) -> None:
    payload = json.dumps(value, default=float)
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM results WHERE key=:k"), {"k": key})
        c.execute(text("INSERT INTO results(key,value,updated_at) VALUES(:k,:v,:t)"), {"k": key, "v": payload, "t": now()})


def kv_get(key: str):
    with get_engine().connect() as c:
        row = c.execute(text("SELECT value FROM results WHERE key=:k"), {"k": key}).fetchone()
    return json.loads(row[0]) if row else None
