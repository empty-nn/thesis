from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.auth import (
    GoogleLoginRequest,
    GoogleLoginResponse,
)
from services.auth import login_with_google


router = APIRouter(tags=["auth"])


@router.post(
    "/auth/google",
    response_model=GoogleLoginResponse,
)
def google_login(
    request: GoogleLoginRequest,
    db: Session = Depends(get_db),
) -> GoogleLoginResponse:
    return login_with_google(
        credential=request.credential,
        db=db,
    )
