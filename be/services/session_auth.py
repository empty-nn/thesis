from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import HTTPException, Request


COOKIE_NAME = "tga_session"
SESSION_SECONDS = 60 * 60 * 24 * 7


def _secret() -> bytes:
    value = os.getenv("AUTH_SESSION_SECRET")
    if not value:
        raise HTTPException(
            status_code=503,
            detail="AUTH_SESSION_SECRET is not configured",
        )
    return value.encode("utf-8")


def create_session_token(user_id: str) -> str:
    payload = json.dumps(
        {
            "user_id": user_id,
            "exp": int(time.time()) + SESSION_SECONDS,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(
        _secret(),
        encoded,
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{encoded.decode()}.{encoded_signature.decode()}"


def optional_session_user_id(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    try:
        encoded, encoded_signature = token.split(".", 1)
        expected = hmac.new(
            _secret(),
            encoded.encode(),
            hashlib.sha256,
        ).digest()
        supplied = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(expected, supplied):
            return None
        payload_bytes = base64.urlsafe_b64decode(
            encoded + "=" * (-len(encoded) % 4)
        )
        payload = json.loads(payload_bytes)
        if int(payload["exp"]) < int(time.time()):
            return None
        return str(payload["user_id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def require_session_user_id(request: Request) -> str:
    user_id = optional_session_user_id(request)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )
    return user_id
