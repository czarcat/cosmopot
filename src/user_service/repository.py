from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .models import Subscription, User, UserProfile, UserSession
from .schemas import (
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
            joinedload(User.subscription),
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


async def create_subscription(
    session: AsyncSession, name: str, level: str, monthly_cost: Decimal
) -> Subscription:
    subscription = Subscription(
        name=name,
        level=level,
        monthly_cost=Decimal(monthly_cost).quantize(Decimal("0.01")),
    )
    session.add(subscription)
    await session.flush()
    await session.refresh(subscription)
    return subscription


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
