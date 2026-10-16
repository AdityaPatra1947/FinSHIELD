"""Auth dependencies: server-side session lookup, role guards, CSRF + Origin checks, audit helper."""
from __future__ import annotations

import hmac
import hashlib
import json
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text

from app.core.config import get_settings
from app.core.security import token_hash
from app.db import get_engine, now

SESSION_COOKIE, CSRF_COOKIE = "fs_session", "fs_csrf"
IDLE_S, ABSOLUTE_S = 30 * 60, 12 * 3600
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def err(status: int, code: str, message: str, **fields):
    return HTTPException(status, {"error": {"code": code, "message": message, "fields": fields}})


@dataclass
class CurrentUser:
    id: str
    email: str
    role: str
    customer_id: int | None
    session_id: str

    @property
    def is_staff(self) -> bool:
        return self.role in ("analyst", "admin")


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().origins:
        raise err(403, "bad_origin", "Request origin not allowed")


def current_user(request: Request) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise err(401, "unauthenticated", "Sign in required")
    t = now()
    with get_engine().begin() as c:
        row = c.execute(text(
            "SELECT s.id, s.csrf_hash, s.idle_expires_at, s.absolute_expires_at, s.revoked_at, "
            "u.id, u.email, u.role, u.customer_id, u.active, s.last_seen_at FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=:h"), {"h": token_hash(token)}).fetchone()
        if (not row or row[4] is not None or not row[9] or row[2] < t or row[3] < t):
            raise err(401, "unauthenticated", "Session expired or invalid")
        if request.method not in SAFE_METHODS:
            check_origin(request)
            hdr, cookie = request.headers.get("x-csrf-token", ""), request.cookies.get(CSRF_COOKIE, "")
            ok = bool(hdr) and hmac.compare_digest(hdr, cookie) and hmac.compare_digest(
                hashlib.sha256(hdr.encode()).hexdigest(), row[1])
            if not ok:
                raise err(403, "csrf_failed", "CSRF check failed")
        # idle renewal never extends the absolute limit; role is read fresh from the user row each request
        if t - row[10] > 60:  # throttle renewal writes (idle window is 30 min)
            c.execute(text("UPDATE sessions SET last_seen_at=:t, idle_expires_at=:i WHERE id=:id"),
                      {"t": t, "i": min(t + IDLE_S, row[3]), "id": row[0]})
    return CurrentUser(id=row[5], email=row[6], role=row[7], customer_id=row[8], session_id=row[0])


def require(*roles: str):
    def dep(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in roles:
            raise err(403, "forbidden", "Action not permitted for your role")
        return user
    return dep


staff = require("analyst", "admin")
admin_only = require("admin")


def authorize_customer(user: CurrentUser, cid: int) -> None:
    """Customer IDs in URLs are selectors, not proof of access; unauthorized -> generic 404."""
    if user.role == "customer" and user.customer_id != cid:
        raise err(404, "not_found", "Resource unavailable")


def audit(user: CurrentUser | None, action: str, object_type: str | None = None, object_id: str | None = None,
          details: dict | None = None, actor_email: str | None = None) -> None:
    with get_engine().begin() as c:
        c.execute(text(
            "INSERT INTO audit_events(actor_id,actor_email,action,object_type,object_id,safe_details,request_id,occurred_at) "
            "VALUES(:a,:e,:ac,:ot,:oi,:d,:r,:t)"),
            {"a": user.id if user else None, "e": user.email if user else actor_email, "ac": action, "ot": object_type,
             "oi": None if object_id is None else str(object_id), "d": json.dumps(details or {}, default=str),
             "r": str(uuid.uuid4()), "t": now()})
