"""Password hashing, opaque session tokens, CSRF tokens, login rate limiting."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.core.config import ConfigError, get_settings

_ph = PasswordHasher()  # Argon2id
DUMMY_HASH = _ph.hash("not-a-real-password")  # constant-ish time for unknown users


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(stored: str | None, pw: str) -> bool:
    try:
        return _ph.verify(stored or DUMMY_HASH, pw) and stored is not None
    except VerificationError:
        return False
    except Exception:
        return False


def _pepper() -> bytes:
    p = get_settings().session_pepper
    if not p:
        raise ConfigError("SESSION_PEPPER missing; run `python -m app.cli seed-users` to generate one in development")
    return p.encode()


def token_hash(token: str) -> str:
    return hmac.new(_pepper(), token.encode(), hashlib.sha256).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def make_pre_csrf() -> str:
    body = f"{int(time.time())}.{secrets.token_urlsafe(16)}"
    return f"{body}.{hmac.new(_pepper(), body.encode(), hashlib.sha256).hexdigest()}"


def check_pre_csrf(token: str | None, max_age: int = 600) -> bool:
    try:
        ts, nonce, sig = (token or "").split(".")
        good = hmac.new(_pepper(), f"{ts}.{nonce}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and time.time() - int(ts) <= max_age
    except Exception:
        return False


def random_password(n: int = 16) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


class RateLimiter:
    """In-process sliding window (local demo). Production needs a shared store / reverse proxy."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def allow(self, key: str) -> bool:
        q, t = self.hits[key], time.time()
        while q and t - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(t)
        return True


login_limiter = RateLimiter(5, 60)
