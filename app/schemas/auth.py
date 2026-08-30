from datetime import date
from enum import Enum

from pydantic import AnyHttpUrl, EmailStr, Field, field_validator

from app.models import Gender
from app.schemas.common import Dto


class AuthProvider(str, Enum):
    google = "google"
    kakao = "kakao"


class AuthUser(Dto):
    id: int = Field(gt=0)
    email: EmailStr
    nickname: str | None = None
    profile_image_url: str | None = Field(default=None, serialization_alias="profileImageUrl")
    birth_date: date | None = Field(default=None, serialization_alias="birthDate")
    gender: Gender | None = None


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


class ProfileUpdateRequest(Dto):
    nickname: str | None = Field(default=None, max_length=30)
    profile_image_key: str | None = Field(
        default=None, max_length=500, validation_alias="profileImageKey"
    )
    birth_date: date | None = Field(default=None, validation_alias="birthDate")
    gender: Gender | None = None

    @field_validator("nickname")
    @classmethod
    def clean_nickname(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else None
        if value is not None and not 2 <= len(value) <= 30:
            raise ValueError("nickname must be between 2 and 30 characters")
        return value or None


class ProfileUploadRequest(Dto):
    content_type: str = Field(validation_alias="contentType")


class ProfileUploadResponse(Dto):
    upload_url: str = Field(serialization_alias="uploadUrl")
    fields: dict[str, str]
    object_key: str = Field(serialization_alias="objectKey")
    expires_in: int = Field(serialization_alias="expiresIn")


class AccountReminderRequest(Dto):
    email: EmailStr


class PasswordResetRequest(Dto):
    email: EmailStr


class PasswordResetConfirm(Dto):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128, validation_alias="newPassword")


class MessageResponse(Dto):
    message: str
