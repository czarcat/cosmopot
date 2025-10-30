from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from . import repository
from .models import User, UserSession
from .schemas import (
    UserCreate,
    UserProfileCreate,
    UserSessionCreate,
    UserUpdate,
)


async def register_user(
    session: AsyncSession,
    user_data: UserCreate,
    profile_data: Optional[UserProfileCreate] = None,
) -> User:
    """Create a user and optional profile within a single transaction."""

    user = await repository.create_user(session, user_data)
    if profile_data is not None:
        enriched = profile_data.model_copy(update={"user_id": user.id})
        await repository.create_profile(session, enriched)
        await session.refresh(user)
    return user


async def update_user_details(
    session: AsyncSession, user: User, updates: UserUpdate
) -> User:
    return await repository.update_user(session, user, updates)


async def adjust_balance_by(
    session: AsyncSession, user: User, delta: Decimal
) -> Decimal:
    new_balance = await repository.adjust_user_balance(session, user.id, delta)
    await session.refresh(user)
    return new_balance


async def soft_delete_account(session: AsyncSession, user: User) -> User:
    return await repository.soft_delete_user(session, user)


async def permanently_delete_account(session: AsyncSession, user: User) -> None:
    await repository.hard_delete_user(session, user)


async def open_session(
    session: AsyncSession, data: UserSessionCreate
) -> UserSession:
    return await repository.create_session(session, data)


async def revoke_session_by_token(
    session: AsyncSession, token: str
) -> Optional[UserSession]:
    return await repository.revoke_session(session, token)


async def expire_session_by_token(
    session: AsyncSession, token: str
) -> Optional[UserSession]:
    return await repository.expire_session(session, token)
