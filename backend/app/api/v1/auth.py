from __future__ import annotations

import hashlib
import hmac
import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import get_settings
from app.core.security import (check_pre_csrf, login_limiter, make_pre_csrf, new_token, token_hash,
                               verify_password)
from app.db import get_engine, now
from app.deps import (ABSOLUTE_S, CSRF_COOKIE, IDLE_S, SESSION_COOKIE, CurrentUser, audit, check_origin,
                      current_user, err)

router = APIRouter(prefix="/auth")
PRE_COOKIE = "fs_csrf_pre"


class LoginBody(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


def _me(u: CurrentUser) -> dict:
    return {"id": u.id, "email": u.email, "role": u.role, "customer_id": u.customer_id}


@router.get("/csrf")
def csrf(response: Response):
    tok = make_pre_csrf()
    response.set_cookie(PRE_COOKIE, tok, max_age=600, httponly=True, samesite="lax",
                        secure=get_settings().cookie_secure, path="/")
    return {"csrf_token": tok}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    check_origin(request)
    hdr = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(PRE_COOKIE, "")
    if not (hdr and hmac.compare_digest(hdr, cookie) and check_pre_csrf(hdr)):
        raise err(403, "csrf_failed", "CSRF check failed")
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "?"
    if not login_limiter.allow(f"{email}|{ip}"):
        raise err(429, "rate_limited", "Too many attempts; try again in a minute")
    with get_engine().begin() as c:
        row = c.execute(text("SELECT id,email,password_hash,role,customer_id,active FROM users WHERE email=:e"),
                        {"e": email}).fetchone()
        ok = verify_password(row[2] if row else None, body.password) and bool(row and row[5])
        if not ok:
            audit(None, "login_failed", "user", None, {}, actor_email=email)
            raise err(401, "invalid_credentials", "Invalid email or password")
        token, csrf_token, t = new_token(), new_token(), now()
        sid = str(uuid.uuid4())
        c.execute(text("INSERT INTO sessions(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,idle_expires_at,"
                       "absolute_expires_at) VALUES(:i,:u,:h,:c,:t,:t,:ie,:ae)"),
                  {"i": sid, "u": row[0], "h": token_hash(token), "c": hashlib.sha256(csrf_token.encode()).hexdigest(),
                   "t": t, "ie": t + IDLE_S, "ae": t + ABSOLUTE_S})
        c.execute(text("UPDATE users SET last_login_at=:t WHERE id=:i"), {"t": t, "i": row[0]})
    secure = get_settings().cookie_secure
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=secure, path="/", max_age=ABSOLUTE_S)
    # readable by the SPA (double-submit); its hash is also bound to the server-side session
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False, samesite="lax", secure=secure, path="/", max_age=ABSOLUTE_S)
    response.delete_cookie(PRE_COOKIE, path="/")
    user = CurrentUser(row[0], row[1], row[3], row[4], sid)
    audit(user, "login", "session", sid)
    return _me(user)


@router.post("/logout", status_code=204)
def logout(response: Response, user: CurrentUser = Depends(current_user)):
    with get_engine().begin() as c:
        c.execute(text("UPDATE sessions SET revoked_at=:t WHERE id=:i"), {"t": now(), "i": user.session_id})
    audit(user, "logout", "session", user.session_id)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)):
    return _me(user)
