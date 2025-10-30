from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .enums import PaymentStatus, SubscriptionStatus, SubscriptionTier, TransactionType
from .models import (
    Payment,
    Subscription,
    SubscriptionHistory,
    SubscriptionPlan,
    Transaction,
    User,
    UserProfile,
    UserSession,
)
from .schemas import (
    PaymentCreate,
    SubscriptionCreate,
    TransactionCreate,
    UserCreate,
    UserProfileCreate,
    UserProfileUpdate,
    UserSessionCreate,
    UserUpdate,
)


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """Persist a new :class:`User` instance."""

    user = User(**data.model_dump())
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user: User, data: UserUpdate) -> User:
    """Update mutable fields for a user instance."""

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(user, key, value)
    await session.flush()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_with_related(session: AsyncSession, user_id: int) -> Optional[User]:
    stmt = (
        select(User)
        .options(
            joinedload(User.profile),
            joinedload(User.sessions),
            joinedload(User.subscription_plan),
            joinedload(User.subscriptions),
        )
        .where(User.id == user_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def adjust_user_balance(session: AsyncSession, user_id: int, delta: Decimal) -> Decimal:
    """Increment a user's balance by a delta amount within a transaction."""

    stmt = select(User).where(User.id == user_id).with_for_update()
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("user not found")

    current_balance = user.balance or Decimal("0")
    updated_balance = current_balance + Decimal(delta)
    quantized = updated_balance.quantize(Decimal("0.01"))
    if quantized < Decimal("0"):
        raise ValueError("balance cannot be negative")

    user.balance = quantized
    await session.flush()
    await session.refresh(user)
    return user.balance


async def soft_delete_user(session: AsyncSession, user: User) -> User:
    user.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    return user


async def hard_delete_user(session: AsyncSession, user: User) -> None:
    await session.delete(user)
    await session.flush()


async def create_subscription_plan(
    session: AsyncSession, name: str, level: str, monthly_cost: Decimal
) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name=name,
        level=level,
        monthly_cost=Decimal(monthly_cost).quantize(Decimal("0.01")),
    )
    session.add(plan)
    await session.flush()
    await session.refresh(plan)
    return plan


async def create_profile(session: AsyncSession, data: UserProfileCreate) -> UserProfile:
    profile = UserProfile(**data.model_dump())
    session.add(profile)
    await session.flush()
    await session.refresh(profile)
    return profile


async def update_profile(
    session: AsyncSession, profile: UserProfile, data: UserProfileUpdate
) -> UserProfile:
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(profile, key, value)
    await session.flush()
    await session.refresh(profile)
    return profile


async def get_profile_by_user_id(session: AsyncSession, user_id: int) -> Optional[UserProfile]:
    stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_session(session: AsyncSession, data: UserSessionCreate) -> UserSession:
    session_model = UserSession(**data.model_dump())
    session.add(session_model)
    await session.flush()
    await session.refresh(session_model)
    return session_model


async def get_active_session_by_token(
    session: AsyncSession, token: str
) -> Optional[UserSession]:
    stmt = select(UserSession).where(
        UserSession.session_token == token, UserSession.revoked_at.is_(None)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def revoke_session(session: AsyncSession, session_token: str) -> Optional[UserSession]:
    user_session = await get_active_session_by_token(session, session_token)
    if user_session is None:
        return None
    user_session.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(user_session)
    return user_session


async def expire_session(session: AsyncSession, session_token: str) -> Optional[UserSession]:
    stmt = select(UserSession).where(UserSession.session_token == session_token)
    result = await session.execute(stmt)
    user_session = result.scalar_one_or_none()
    if user_session is None:
        return None
    user_session.ended_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(user_session)
    return user_session


async def create_subscription(
    session: AsyncSession, data: SubscriptionCreate
) -> Subscription:
    """Persist a new subscription record for a user."""

    payload = data.model_dump()
    payload["tier"] = SubscriptionTier(payload["tier"])
    payload["status"] = SubscriptionStatus(payload["status"])
    payload["provider_data"] = dict(payload.get("provider_data") or {})
    payload["metadata"] = dict(payload.get("metadata") or {})

    subscription = Subscription(**payload)
    session.add(subscription)
    await session.flush()
    await session.refresh(subscription)
    return subscription


async def get_subscription_by_id(
    session: AsyncSession, subscription_id: int
) -> Optional[Subscription]:
    stmt = select(Subscription).where(Subscription.id == subscription_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_subscription_history_snapshot(
    session: AsyncSession,
    subscription: Subscription,
    *,
    reason: Optional[str] = None,
) -> SubscriptionHistory:
    """Capture the current state of a subscription in the history table."""

    snapshot = SubscriptionHistory(
        subscription_id=subscription.id,
        tier=subscription.tier,
        status=subscription.status,
        auto_renew=subscription.auto_renew,
        quota_limit=subscription.quota_limit,
        quota_used=subscription.quota_used,
        provider_subscription_id=subscription.provider_subscription_id,
        provider_data=dict(subscription.provider_data or {}),
        metadata=dict(subscription.metadata or {}),
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        reason=reason,
    )
    session.add(snapshot)
    await session.flush()
    await session.refresh(snapshot)
    return snapshot


async def increment_subscription_usage(
    session: AsyncSession, subscription: Subscription, amount: int
) -> Subscription:
    """Accumulate usage against the subscription's quota within a transaction."""

    if amount < 0:
        raise ValueError("amount must be non-negative")
    updated = subscription.quota_used + amount
    if updated > subscription.quota_limit:
        raise ValueError("quota usage exceeds configured limit")
    subscription.quota_used = updated
    await session.flush()
    await session.refresh(subscription)
    return subscription


async def create_payment(session: AsyncSession, data: PaymentCreate) -> Payment:
    payload = data.model_dump()
    payload["status"] = PaymentStatus(payload["status"])
    payload["provider_data"] = dict(payload.get("provider_data") or {})
    payload["metadata"] = dict(payload.get("metadata") or {})
    payment = Payment(**payload)
    session.add(payment)
    await session.flush()
    await session.refresh(payment)
    return payment


async def create_transaction(
    session: AsyncSession, *, payment_id: int, data: TransactionCreate
) -> Transaction:
    payload = data.model_dump()
    payload["payment_id"] = payment_id
    payload["type"] = TransactionType(payload["type"])
    payload["metadata"] = dict(payload.get("metadata") or {})
    transaction = Transaction(**payload)
    session.add(transaction)
    await session.flush()
    await session.refresh(transaction)
    return transaction
