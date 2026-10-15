from datetime import datetime, timezone
from typing import Literal
import re

from pydantic import Field, StrictBool, field_validator, field_serializer

from app.models import TeeClaimStatus
from app.schemas.common import Dto, OrmDto


class TeeClaimCreate(Dto):
    size: Literal["S", "M", "L", "XL", "2XL"]
    recipient_name: str = Field(min_length=1, max_length=100, validation_alias="recipientName")
    phone_number: str = Field(min_length=9, max_length=30, validation_alias="phoneNumber")
    postal_code: str = Field(pattern=r"^[0-9]{5}$", validation_alias="postalCode")
    address: str = Field(min_length=5, max_length=500)
    address_detail: str = Field(default="", max_length=200, validation_alias="addressDetail")
    shipping_consent: StrictBool = Field(validation_alias="shippingConsent")

    @field_validator(
        "recipient_name", "phone_number", "postal_code", "address", "address_detail", mode="before"
    )
    @classmethod
    def clean(cls, value):
        if not isinstance(value, str):
            raise ValueError("Text is required")
        return value.strip()

    @field_validator("phone_number")
    @classmethod
    def phone(cls, value):
        value = re.sub(r"[\s()-]", "", value)
        if not re.fullmatch(r"0[0-9]{8,10}", value):
            raise ValueError("Invalid phone number")
        return value

    @field_validator("shipping_consent")
    @classmethod
    def consent(cls, value):
        if not value:
            raise ValueError("Shipping consent is required")
        return value


class TeeClaimResponse(OrmDto):
    @field_serializer("requested_at", "fulfilled_at", check_fields=False)
    def utc_datetime(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat() if value is not None else None

    id: int
    allocation_no: int = Field(serialization_alias="allocationNo")
    size: str
    recipient_name: str = Field(serialization_alias="recipientName")
    phone_number: str = Field(serialization_alias="phoneNumber")
    postal_code: str = Field(serialization_alias="postalCode")
    address: str
    address_detail: str = Field(serialization_alias="addressDetail")
    status: TeeClaimStatus
    requested_at: datetime = Field(serialization_alias="requestedAt")
    fulfilled_at: datetime | None = Field(serialization_alias="fulfilledAt")


class TeeRewardResponse(Dto):
    required_stamps: int = Field(serialization_alias="requiredStamps")
    collected_stamps: int = Field(serialization_alias="collectedStamps")
    quantity: int
    remaining: int
    is_open: bool = Field(serialization_alias="isOpen")
    eligible: bool
    can_manage: bool = Field(serialization_alias="canManage")
    claim: TeeClaimResponse | None


class TeeClaimPatch(Dto):
    status: TeeClaimStatus
