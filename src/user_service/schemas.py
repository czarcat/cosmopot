from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .enums import UserRole


def _quantize_two_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class UserCreate(BaseModel):
    email: EmailStr
    hashed_password: str = Field(..., min_length=8, max_length=255)
    role: UserRole = UserRole.USER
    balance: Decimal = Decimal("0.00")
    subscription_id: Optional[int] = None
    is_active: bool = True

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("balance", mode="before")
    @classmethod
    def validate_balance(cls, value: Decimal | str | int | float) -> Decimal:
        decimal_value = Decimal(str(value))
        if decimal_value < Decimal("0"):
            raise ValueError("balance cannot be negative")
        return _quantize_two_places(decimal_value)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    hashed_password: Optional[str] = Field(None, min_length=8, max_length=255)
    role: Optional[UserRole] = None
    balance: Optional[Decimal] = None
    subscription_id: Optional[int] = None
    is_active: Optional[bool] = None
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("balance", mode="before")
    @classmethod
    def validate_balance(cls, value: Optional[Decimal | str | int | float]) -> Optional[Decimal]:
        if value is None:
            return None
        return _quantize_two_places(Decimal(str(value)))


class UserRead(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    balance: Decimal
    subscription_id: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class UserProfileBase(BaseModel):
    first_name: Optional[str] = Field(None, max_length=120)
    last_name: Optional[str] = Field(None, max_length=120)
    telegram_id: Optional[int] = Field(None, ge=1)
    phone_number: Optional[str] = Field(None, max_length=40)
    country: Optional[str] = Field(None, max_length=80)
    city: Optional[str] = Field(None, max_length=80)


class UserProfileCreate(UserProfileBase):
    user_id: int


class UserProfileUpdate(UserProfileBase):
    pass


class UserProfileRead(UserProfileBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class UserSessionCreate(BaseModel):
    user_id: int
    session_token: str = Field(..., min_length=16, max_length=255)
    user_agent: Optional[str] = Field(None, max_length=255)
    ip_address: Optional[str] = Field(None, max_length=45)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def ensure_future(cls, value: datetime) -> datetime:
        candidate = value
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=timezone.utc)
        candidate_utc = candidate.astimezone(timezone.utc)
        if candidate_utc <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return candidate_utc


class UserSessionRead(BaseModel):
    id: int
    user_id: int
    session_token: str
    user_agent: Optional[str]
    ip_address: Optional[str]
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime]
    ended_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class UserWithProfile(UserRead):
    profile: Optional[UserProfileRead] = None
    sessions: List[UserSessionRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
