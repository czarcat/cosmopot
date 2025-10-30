from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from secrets import token_hex
from typing import Optional

from user_service.enums import UserRole
from user_service.schemas import (
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
