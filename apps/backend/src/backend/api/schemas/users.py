from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from user_service.enums import UserRole

__all__ = [
    "QuotaSummary",
    "SubscriptionSummary",
    "SessionStatus",
    "SessionResponse",
    "UserProfilePayload",
    "UserProfileResponse",
    "UserResponse",
    "BalanceAdjustmentRequest",
    "BalanceResponse",
    "RoleUpdateRequest",
    "GDPRRequestResponse",
]


class QuotaSummary(BaseModel):
    plan: str = Field(..., description="Human readable subscription level, or 'free'.")
    monthly_allocation: int = Field(
        ..., ge=0, description="Placeholder quota for included credits per month."
    )
    remaining_allocation: int = Field(
        ..., ge=0, description="Placeholder for remaining credits after consumption."
    )
    requires_top_up: bool = Field(
        ...,
        description="Indicates whether balance is low enough to trigger a top-up warning.",
    )

    model_config = ConfigDict(extra="forbid")


class SubscriptionSummary(BaseModel):
    id: int
    name: str
    level: str
    monthly_cost: Decimal

    model_config = ConfigDict(from_attributes=True)


class SessionStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class SessionResponse(BaseModel):
    id: int
    session_token: str
    user_agent: Optional[str]
    ip_address: Optional[str]
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime]
    ended_at: Optional[datetime]
    status: SessionStatus

    model_config = ConfigDict(from_attributes=True)


class UserProfilePayload(BaseModel):
    first_name: Optional[str] = Field(None, max_length=120)
    last_name: Optional[str] = Field(None, max_length=120)
    telegram_id: Optional[int] = Field(None, ge=1)
    phone_number: Optional[str] = Field(None, max_length=40)
    country: Optional[str] = Field(None, max_length=80)
    city: Optional[str] = Field(None, max_length=80)

    model_config = ConfigDict(extra="forbid")


class UserProfileResponse(UserProfilePayload):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    balance: Decimal
    is_active: bool
    subscription: Optional[SubscriptionSummary]
    quotas: QuotaSummary
    profile: Optional[UserProfileResponse]
    sessions: list[SessionResponse]

    model_config = ConfigDict(from_attributes=True)


class BalanceAdjustmentRequest(BaseModel):
    delta: Decimal = Field(
        ..., description="Signed decimal amount applied to the balance."
    )
    reason: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional audit trail message for the adjustment.",
    )

    model_config = ConfigDict(extra="forbid")


class BalanceResponse(BaseModel):
    balance: Decimal
    quotas: QuotaSummary

    model_config = ConfigDict(extra="forbid")


class RoleUpdateRequest(BaseModel):
    role: UserRole

    model_config = ConfigDict(extra="forbid")


class GDPRRequestResponse(BaseModel):
    status: str
    requested_at: datetime
    reference: str
    note: Optional[str] = None

    model_config = ConfigDict(extra="forbid")
