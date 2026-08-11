from datetime import datetime

from pydantic import Field

from schemas.camel_model import CamelModel


class GoogleLoginRequest(CamelModel):
    credential: str = Field(min_length=1)


class AuthUser(CamelModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    profile_picture_url: str | None = None


class GoogleLoginResponse(CamelModel):
    user: AuthUser
    is_new_user: bool
    authenticated_at: datetime


class SessionResponse(CamelModel):
    user: AuthUser
