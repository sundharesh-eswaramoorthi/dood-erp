from __future__ import annotations

import datetime as dt

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()
_ALGO = "HS256"


def hash_password(raw: str) -> str:
    return _ph.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, raw)
    except VerifyMismatchError:
        return False


def _encode(sub: str, typ: str, ttl: dt.timedelta, claims: dict | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(sub),
        "typ": typ,
        "iat": now,
        "exp": now + ttl,
        **(claims or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGO)


def create_access_token(sub: str, claims: dict) -> str:
    return _encode(sub, "access", dt.timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN), claims)


def create_refresh_token(sub: str) -> str:
    return _encode(sub, "refresh", dt.timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS))


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGO])
