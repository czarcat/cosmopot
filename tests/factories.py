from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from secrets import token_hex
from typing import Any, Dict, Optional

from user_service.enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PaymentStatus,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
    UserRole,
)
from user_service.schemas import (
    GenerationTaskCreate,
    GenerationTaskFailureUpdate,
    GenerationTaskResultUpdate,
    PaymentCreate,
    PromptCreate,
    SubscriptionCreate,
    SubscriptionRenew,
    TransactionCreate,
    UserCreate,
    UserProfileCreate,
    UserSessionCreate,
)

_counter = count(1)


def user_create_factory(
    *, email: Optional[str] = None, role: UserRole = UserRole.USER
) -> UserCreate:
    index = next(_counter)
    return UserCreate(
        email=email or f"user{index}@example.com",
        hashed_password="hashed-password-value",
        role=role,
        balance=Decimal("0.00"),
        subscription_id=None,
        is_active=True,
    )


def user_profile_create_factory(
    user_id: int, *, telegram_id: Optional[int] = None
) -> UserProfileCreate:
    index = next(_counter)
    return UserProfileCreate(
        user_id=user_id,
        first_name=f"First{index}",
        last_name=f"Last{index}",
        telegram_id=telegram_id or 1_000_000 + index,
        phone_number="+123456789",
        country="Wonderland",
        city="Hearts",
    )


def user_session_create_factory(user_id: int, *, expires_in: int = 3600) -> UserSessionCreate:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return UserSessionCreate(
        user_id=user_id,
        session_token=token_hex(16),
        user_agent="pytest",
        ip_address="127.0.0.1",
        expires_at=expires_at,
    )


def subscription_create_factory(
    user_id: int,
    *,
    tier: SubscriptionTier = SubscriptionTier.STANDARD,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    auto_renew: bool = True,
    quota_limit: int = 1_000,
    quota_used: int = 0,
    period_days: int = 30,
    provider_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SubscriptionCreate:
    index = next(_counter)
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=period_days)
    return SubscriptionCreate(
        user_id=user_id,
        tier=tier,
        status=status,
        auto_renew=auto_renew,
        quota_limit=quota_limit,
        quota_used=quota_used,
        provider_subscription_id=f"sub_{index}",
        provider_data=provider_metadata or {"cycle": index},
        metadata=metadata or {"source": "tests"},
        current_period_start=start,
        current_period_end=end,
    )


def subscription_renew_factory(
    *,
    days: int = 30,
    quota_limit: Optional[int] = None,
    provider_data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = "renewal",
) -> SubscriptionRenew:
    end = datetime.now(timezone.utc) + timedelta(days=days)
    return SubscriptionRenew(
        new_period_end=end,
        quota_limit=quota_limit,
        provider_data=provider_data or {"cycle": "renewal"},
        metadata=metadata or {"note": "renewal"},
        reason=reason,
    )


def payment_create_factory(
    user_id: int,
    subscription_id: Optional[int],
    *,
    amount: Decimal = Decimal("19.99"),
    currency: str = "usd",
    status: PaymentStatus = PaymentStatus.COMPLETED,
    provider_payment_id: Optional[str] = None,
    provider_data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> PaymentCreate:
    index = next(_counter)
    return PaymentCreate(
        user_id=user_id,
        subscription_id=subscription_id,
        amount=amount,
        currency=currency,
        status=status,
        provider_payment_id=provider_payment_id or f"pm_{index}",
        provider_data=provider_data or {"processor": "stripe"},
        metadata=metadata or {"note": "test"},
        paid_at=datetime.now(timezone.utc),
    )


def transaction_create_factory(
    user_id: int,
    subscription_id: Optional[int],
    *,
    amount: Decimal = Decimal("19.99"),
    currency: str = "usd",
    txn_type: TransactionType = TransactionType.CHARGE,
    description: Optional[str] = None,
    provider_reference: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TransactionCreate:
    index = next(_counter)
    return TransactionCreate(
        subscription_id=subscription_id,
        user_id=user_id,
        amount=amount,
        currency=currency,
        type=txn_type,
        description=description or "Test transaction",
        provider_reference=provider_reference or f"txn_{index}",
        metadata=metadata or {"note": "test-transaction"},
    )


def prompt_create_factory(
    *,
    slug: Optional[str] = None,
    source: PromptSource = PromptSource.SYSTEM,
    parameters: Optional[Dict[str, Any]] = None,
) -> PromptCreate:
    index = next(_counter)
    return PromptCreate(
        slug=slug or f"prompt-{index}",
        name=f"Prompt {index}",
        description="Default prompt used for tests",
        source=source,
        parameters=parameters or {"temperature": 0.5},
        preview_asset_url=f"s3://prompts/{index}/preview.png",
    )


def generation_task_create_factory(
    user_id: int,
    prompt_id: int,
    *,
    status: GenerationTaskStatus = GenerationTaskStatus.PENDING,
    source: GenerationTaskSource = GenerationTaskSource.API,
    parameters: Optional[Dict[str, Any]] = None,
) -> GenerationTaskCreate:
    index = next(_counter)
    return GenerationTaskCreate(
        user_id=user_id,
        prompt_id=prompt_id,
        status=status,
        source=source,
        parameters=parameters or {"size": "1024x1024"},
        result_parameters={},
        input_asset_url=f"s3://tasks/{index}/input.json",
        result_asset_url=None,
    )


def generation_task_result_update_factory(
    *,
    result_asset_url: Optional[str] = None,
    result_parameters: Optional[Dict[str, Any]] = None,
) -> GenerationTaskResultUpdate:
    return GenerationTaskResultUpdate(
        result_asset_url=result_asset_url or "s3://tasks/results/output.png",
        result_parameters=result_parameters or {"duration": 1.23},
    )


def generation_task_failure_update_factory(
    *,
    error: str = "task failed",
    result_asset_url: Optional[str] = None,
    result_parameters: Optional[Dict[str, Any]] = None,
) -> GenerationTaskFailureUpdate:
    return GenerationTaskFailureUpdate(
        error=error,
        result_asset_url=result_asset_url or "s3://tasks/results/error.log",
        result_parameters=result_parameters or {"retries": 3},
    )
