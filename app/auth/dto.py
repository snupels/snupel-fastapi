from datetime import date
from enum import Enum

from pydantic import AnyHttpUrl, EmailStr, Field

from app.dto import Dto
from app.models import Gender


class AuthProvider(str, Enum):
    google = "google"
    kakao = "kakao"


class AuthUser(Dto):
    id: int = Field(gt=0)
    email: EmailStr


class AuthResponse(Dto):
    access_token: str = Field(serialization_alias="accessToken")
    token_type: str = Field(default="Bearer", serialization_alias="tokenType")
    expires_in: int = Field(gt=0, serialization_alias="expiresIn")
    user: AuthUser


class SignupRequest(Dto):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    birth_date: date | None = Field(default=None, validation_alias="birthDate")
    gender: Gender | None = None


class LoginRequest(Dto):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class OAuthAuthorizeResponse(Dto):
    provider: AuthProvider
    authorization_url: AnyHttpUrl = Field(serialization_alias="authorizationUrl")


class OAuthLoginRequest(Dto):
    code: str = Field(min_length=1)
    redirect_uri: AnyHttpUrl = Field(validation_alias="redirectUri")
    state: str = Field(min_length=1)

