from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PaymentStatus,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
)
from .models import (
    GenerationTask,
    Payment,
    Prompt,
    Subscription,
    SubscriptionHistory,
    SubscriptionPlan,
    Transaction,
    User,
    UserProfile,
    UserSession,
)
from .schemas import (
    GenerationTaskCreate,
    GenerationTaskFailureUpdate,
    GenerationTaskResultUpdate,
    PaymentCreate,
    PromptCreate,
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


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_with_related(session: AsyncSession, user_id: int) -> User | None:
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


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def adjust_user_balance(
    session: AsyncSession, user_id: int, delta: Decimal
) -> Decimal:
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
    user.deleted_at = datetime.now(UTC)
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


async def get_profile_by_user_id(
    session: AsyncSession, user_id: int
) -> UserProfile | None:
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
) -> UserSession | None:
    stmt = select(UserSession).where(
        UserSession.session_token == token, UserSession.revoked_at.is_(None)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def revoke_session(
    session: AsyncSession, session_token: str
) -> UserSession | None:
    user_session = await get_active_session_by_token(session, session_token)
    if user_session is None:
        return None
    user_session.revoked_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(user_session)
    return user_session


async def expire_session(
    session: AsyncSession, session_token: str
) -> UserSession | None:
    stmt = select(UserSession).where(UserSession.session_token == session_token)
    result = await session.execute(stmt)
    user_session = result.scalar_one_or_none()
    if user_session is None:
        return None
    user_session.ended_at = datetime.now(UTC)
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
) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.id == subscription_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_subscription_history_snapshot(
    session: AsyncSession,
    subscription: Subscription,
    *,
    reason: str | None = None,
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


async def decrement_subscription_usage(
    session: AsyncSession, subscription: Subscription, amount: int
) -> Subscription:
    """Reduce quota usage, clamping to zero to avoid negative values."""

    if amount < 0:
        raise ValueError("amount must be non-negative")
    updated = subscription.quota_used - amount
    if updated < 0:
        updated = 0
    subscription.quota_used = updated
    await session.flush()
    await session.refresh(subscription)
    return subscription


async def get_active_subscription_for_user(
    session: AsyncSession, user_id: int
) -> Subscription | None:
    stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status.in_(
                [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
            ),
        )
        .order_by(Subscription.current_period_end.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().first()


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


async def create_prompt(session: AsyncSession, data: PromptCreate) -> Prompt:
    """Persist a prompt template definition."""

    payload = data.model_dump()
    payload["source"] = PromptSource(payload["source"])
    payload["parameters"] = dict(payload.get("parameters") or {})

    prompt = Prompt(**payload)
    session.add(prompt)
    await session.flush()
    await session.refresh(prompt)
    return prompt


async def get_prompt_by_slug(session: AsyncSession, slug: str) -> Prompt | None:
    stmt = select(Prompt).where(Prompt.slug == slug)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_generation_task(
    session: AsyncSession, data: GenerationTaskCreate
) -> GenerationTask:
    """Create a generation task tied to a user and prompt."""

    payload = data.model_dump()
    payload["status"] = GenerationTaskStatus(payload["status"])
    payload["source"] = GenerationTaskSource(payload["source"])
    payload["parameters"] = dict(payload.get("parameters") or {})
    payload["result_parameters"] = dict(payload.get("result_parameters") or {})

    task = GenerationTask(**payload)
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return task


async def get_generation_task_by_id(
    session: AsyncSession, task_id: int
) -> GenerationTask | None:
    stmt = select(GenerationTask).where(GenerationTask.id == task_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _ensure_transition_allowed(task: GenerationTask) -> None:
    if task.status in {
        GenerationTaskStatus.SUCCEEDED,
        GenerationTaskStatus.FAILED,
        GenerationTaskStatus.CANCELED,
    }:
        raise ValueError("task is in a terminal state")


async def mark_generation_task_queued(
    session: AsyncSession, task: GenerationTask
) -> GenerationTask:
    """Mark a pending task as queued for processing."""

    _ensure_transition_allowed(task)
    now = datetime.now(UTC)
    if task.status != GenerationTaskStatus.QUEUED:
        task.status = GenerationTaskStatus.QUEUED
    if task.queued_at is None:
        task.queued_at = now
    await session.flush()
    await session.refresh(task)
    return task


async def mark_generation_task_started(
    session: AsyncSession, task: GenerationTask
) -> GenerationTask:
    """Mark a queued task as actively running."""

    _ensure_transition_allowed(task)
    now = datetime.now(UTC)
    task.status = GenerationTaskStatus.RUNNING
    if task.queued_at is None:
        task.queued_at = now
    task.started_at = now
    await session.flush()
    await session.refresh(task)
    return task


async def mark_generation_task_succeeded(
    session: AsyncSession,
    task: GenerationTask,
    data: GenerationTaskResultUpdate,
) -> GenerationTask:
    """Mark a running task as succeeded and persist resulting artifacts."""

    _ensure_transition_allowed(task)
    if task.status not in {
        GenerationTaskStatus.RUNNING,
        GenerationTaskStatus.QUEUED,
        GenerationTaskStatus.PENDING,
    }:
        raise ValueError("task must be running or queued to complete")

    now = datetime.now(UTC)
    updates = data.model_dump(exclude_unset=True)

    task.status = GenerationTaskStatus.SUCCEEDED
    task.error = None
    task.completed_at = now
    task.result_asset_url = updates.get("result_asset_url", task.result_asset_url)
    if "result_parameters" in updates:
        task.result_parameters = dict(updates["result_parameters"] or {})

    await session.flush()
    await session.refresh(task)
    return task


async def mark_generation_task_failed(
    session: AsyncSession,
    task: GenerationTask,
    data: GenerationTaskFailureUpdate,
) -> GenerationTask:
    """Mark a task as failed with an error message."""

    _ensure_transition_allowed(task)

    now = datetime.now(UTC)
    updates = data.model_dump(exclude_unset=True)

    task.status = GenerationTaskStatus.FAILED
    task.error = updates["error"]
    task.completed_at = now
    task.result_asset_url = updates.get("result_asset_url", task.result_asset_url)
    if "result_parameters" in updates:
        task.result_parameters = dict(updates["result_parameters"] or {})

    await session.flush()
    await session.refresh(task)
    return task
