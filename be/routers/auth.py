from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.auth import (
    GoogleLoginRequest,
    GoogleLoginResponse,
    SessionResponse,
)
from services.auth import login_with_google
from services.session_auth import (
    COOKIE_NAME,
    SESSION_SECONDS,
    create_session_token,
    optional_session_user_id,
)
from db.full_model import UserORM


router = APIRouter(tags=["auth"])


@router.post(
    "/auth/google",
    response_model=GoogleLoginResponse,
)
def google_login(
    request: GoogleLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> GoogleLoginResponse:
    result = login_with_google(
        credential=request.credential,
        db=db,
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session_token(result.user.id),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return result


@router.get("/auth/me", response_model=SessionResponse)
def auth_me(
    request: Request,
    db: Session = Depends(get_db),
) -> SessionResponse:
    user_id = optional_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.scalar(select(UserORM).where(UserORM.id == user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return SessionResponse(
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "profile_picture_url": user.profile_picture_url,
        }
    )


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
