from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from .enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PaymentStatus,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
    UserRole,
)


def _quantize_two_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    raise ValueError("value must be a mapping")


def _coerce_optional_mapping(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    raise ValueError("value must be a mapping")


def _validate_s3_uri(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("S3 URL must be a string")
    if not value.startswith("s3://"):
        raise ValueError("URL must use the s3:// scheme")
    if len(value) <= 5:
        raise ValueError("S3 URL must include a bucket and key")
    return value


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
    def validate_balance(
        cls, value: Optional[Decimal | str | int | float]
    ) -> Optional[Decimal]:
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


class PromptCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1024)
    source: PromptSource = PromptSource.SYSTEM
    parameters: Dict[str, Any] = Field(default_factory=dict)
    preview_asset_url: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, value: Any) -> Dict[str, Any]:
        return _coerce_mapping(value)

    @field_validator("preview_asset_url")
    @classmethod
    def validate_preview_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_s3_uri(value)


class PromptRead(PromptCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class GenerationTaskCreate(BaseModel):
    user_id: int
    prompt_id: int
    status: GenerationTaskStatus = GenerationTaskStatus.PENDING
    source: GenerationTaskSource = GenerationTaskSource.API
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result_parameters: Dict[str, Any] = Field(default_factory=dict)
    input_asset_url: Optional[str] = None
    result_asset_url: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, value: Any) -> Dict[str, Any]:
        return _coerce_mapping(value)

    @field_validator("result_parameters", mode="before")
    @classmethod
    def validate_result_parameters(cls, value: Any) -> Dict[str, Any]:
        return _coerce_mapping(value)

    @field_validator("input_asset_url")
    @classmethod
    def validate_input_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_s3_uri(value)

    @field_validator("result_asset_url")
    @classmethod
    def validate_result_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_s3_uri(value)


class GenerationTaskRead(BaseModel):
    id: int
    user_id: int
    prompt_id: int
    status: GenerationTaskStatus
    source: GenerationTaskSource
    parameters: Dict[str, Any]
    result_parameters: Dict[str, Any]
    input_asset_url: Optional[str]
    result_asset_url: Optional[str]
    error: Optional[str]
    queued_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class GenerationTaskResultUpdate(BaseModel):
    result_asset_url: Optional[str] = None
    result_parameters: Optional[Dict[str, Any]] = None

    @field_validator("result_asset_url")
    @classmethod
    def validate_result_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_s3_uri(value)

    @field_validator("result_parameters", mode="before")
    @classmethod
    def validate_result_parameters(cls, value: Any) -> Optional[Dict[str, Any]]:
        return _coerce_optional_mapping(value)


class GenerationTaskFailureUpdate(BaseModel):
    error: str = Field(..., min_length=1, max_length=500)
    result_asset_url: Optional[str] = None
    result_parameters: Optional[Dict[str, Any]] = None

    @field_validator("result_asset_url")
    @classmethod
    def validate_result_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_s3_uri(value)

    @field_validator("result_parameters", mode="before")
    @classmethod
    def validate_result_parameters(cls, value: Any) -> Optional[Dict[str, Any]]:
        return _coerce_optional_mapping(value)
