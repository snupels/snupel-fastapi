from datetime import date
import re
from enum import Enum
from typing import Literal

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
    phone_number: str | None = Field(default=None, serialization_alias="phoneNumber")
    profile_image_url: str | None = Field(default=None, serialization_alias="profileImageUrl")
    birth_date: date | None = Field(default=None, serialization_alias="birthDate")
    gender: Gender | None = None
    onboarding_required: bool = Field(default=True, serialization_alias="onboardingRequired")
    marketing_email_agreed: bool = Field(
        default=False, serialization_alias="marketingEmailAgreed"
    )
    marketing_sns_agreed: bool = Field(
        default=False, serialization_alias="marketingSnsAgreed"
    )


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
    nickname: str = Field(min_length=2, max_length=30)
    phone_number: str = Field(min_length=10, max_length=13, validation_alias="phoneNumber")
    agree_terms: Literal[True] = Field(validation_alias="agreeTerms")
    agree_privacy: Literal[True] = Field(validation_alias="agreePrivacy")
    agree_marketing_email: bool = Field(
        default=False, validation_alias="agreeMarketingEmail"
    )
    agree_marketing_sns: bool = Field(
        default=False, validation_alias="agreeMarketingSns"
    )

    @field_validator("phone_number")
    @classmethod
    def clean_phone_number(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if not re.fullmatch(r"01[016789]\d{7,8}", digits):
            raise ValueError("phoneNumber must be a valid Korean mobile number")
        return digits


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
    phone_number: str | None = Field(
        default=None, min_length=10, max_length=13, validation_alias="phoneNumber"
    )
    profile_image_key: str | None = Field(
        default=None, max_length=500, validation_alias="profileImageKey"
    )
    birth_date: date | None = Field(default=None, validation_alias="birthDate")
    gender: Gender | None = None
    agree_terms: Literal[True] | None = Field(
        default=None, validation_alias="agreeTerms"
    )
    agree_privacy: Literal[True] | None = Field(
        default=None, validation_alias="agreePrivacy"
    )
    agree_marketing_email: bool | None = Field(
        default=None, validation_alias="agreeMarketingEmail"
    )
    agree_marketing_sns: bool | None = Field(
        default=None, validation_alias="agreeMarketingSns"
    )

    @field_validator("nickname")
    @classmethod
    def clean_nickname(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else None
        if value is not None and not 2 <= len(value) <= 30:
            raise ValueError("nickname must be between 2 and 30 characters")
        return value or None

    @field_validator("phone_number")
    @classmethod
    def clean_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", value)
        if not re.fullmatch(r"01[016789]\d{7,8}", digits):
            raise ValueError("phoneNumber must be a valid Korean mobile number")
        return digits


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


class PasswordVerifyRequest(Dto):
    current_password: str = Field(min_length=1, max_length=128, validation_alias="currentPassword")


class PasswordChangeRequest(PasswordVerifyRequest):
    new_password: str = Field(min_length=8, max_length=128, validation_alias="newPassword")


class MessageResponse(Dto):
    message: str
