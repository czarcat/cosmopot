from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .enums import (
    PaymentStatus,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
    UserRole,
)


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


class SubscriptionCreate(BaseModel):
    user_id: int
    tier: SubscriptionTier
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    auto_renew: bool = True
    quota_limit: int = Field(0, ge=0)
    quota_used: int = Field(0, ge=0)
    provider_subscription_id: Optional[str] = Field(None, max_length=120)
    provider_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    current_period_start: datetime
    current_period_end: datetime

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("current_period_start", "current_period_end", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if isinstance(value, datetime):
            candidate = value
        else:
            candidate = datetime.fromisoformat(str(value))
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=timezone.utc)
        return candidate.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_period(self) -> "SubscriptionCreate":
        if self.current_period_end <= self.current_period_start:
            raise ValueError("current_period_end must be after current_period_start")
        if self.quota_used > self.quota_limit:
            raise ValueError("quota_used cannot exceed quota_limit")
        return self


class SubscriptionRenew(BaseModel):
    new_period_end: datetime
    quota_limit: Optional[int] = Field(None, ge=0)
    provider_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = Field(None, max_length=255)

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("new_period_end", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if isinstance(value, datetime):
            candidate = value
        else:
            candidate = datetime.fromisoformat(str(value))
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=timezone.utc)
        return candidate.astimezone(timezone.utc)


class PaymentCreate(BaseModel):
    user_id: int
    subscription_id: Optional[int] = None
    amount: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    status: PaymentStatus = PaymentStatus.COMPLETED
    provider_payment_id: Optional[str] = Field(None, max_length=120)
    provider_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    paid_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: Decimal | str | int | float) -> Decimal:
        decimal_value = Decimal(str(value))
        if decimal_value < Decimal("0"):
            raise ValueError("amount cannot be negative")
        return _quantize_two_places(decimal_value)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("paid_at", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value is None:
            candidate = datetime.now(timezone.utc)
        elif isinstance(value, datetime):
            candidate = value
        else:
            candidate = datetime.fromisoformat(str(value))
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=timezone.utc)
        return candidate.astimezone(timezone.utc)


class TransactionCreate(BaseModel):
    subscription_id: Optional[int]
    user_id: int
    amount: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    type: TransactionType = TransactionType.CHARGE
    description: Optional[str] = Field(None, max_length=255)
    provider_reference: Optional[str] = Field(None, max_length=120)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: Decimal | str | int | float) -> Decimal:
        return _quantize_two_places(Decimal(str(value)))

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()
