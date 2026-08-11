from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.full_model import UserORM
from schemas.auth import AuthUser, GoogleLoginResponse


def verify_google_credential(credential: str) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")

    if not client_id:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_CLIENT_ID is not configured",
        )

    try:
        from google.auth.transport import requests
        from google.oauth2 import id_token
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Google authentication dependency is not installed",
        ) from exc

    try:
        claims = id_token.verify_oauth2_token(
            credential,
            requests.Request(),
            client_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid Google credential",
        ) from exc

    if not claims.get("sub"):
        raise HTTPException(
            status_code=401,
            detail="Google credential has no subject identifier",
        )

    if not claims.get("email_verified"):
        raise HTTPException(
            status_code=401,
            detail="Google email is not verified",
        )

    return claims


def login_with_google(
    credential: str,
    db: Session,
) -> GoogleLoginResponse:
    claims = verify_google_credential(
        credential
    )
    google_subject = str(claims["sub"])
    email = claims.get("email")

    user = db.scalar(
        select(UserORM).where(
            UserORM.google_subject
            == google_subject
        )
    )
    is_new_user = user is None

    if user is None and email:
        existing_email_user = db.scalar(
            select(UserORM).where(
                func.lower(UserORM.email)
                == email.lower()
            )
        )

        if existing_email_user:
            raise HTTPException(
                status_code=409,
                detail=(
                    "An account already uses this email. "
                    "Automatic account linking is disabled."
                ),
            )

    now = datetime.now(timezone.utc).replace(
        tzinfo=None
    )

    if user is None:
        user = UserORM(
            google_subject=google_subject,
            email=email,
            display_name=claims.get("name"),
            profile_picture_url=claims.get("picture"),
            last_login_at=now,
            is_active=True,
        )
        db.add(user)
    else:
        user.email = email
        user.display_name = claims.get("name")
        user.profile_picture_url = claims.get(
            "picture"
        )
        user.last_login_at = now

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to create the Google account",
        ) from exc

    db.refresh(user)

    return GoogleLoginResponse(
        user=AuthUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            profile_picture_url=(
                user.profile_picture_url
            ),
        ),
        is_new_user=is_new_user,
        authenticated_at=datetime.now(
            timezone.utc
        ),
    )
