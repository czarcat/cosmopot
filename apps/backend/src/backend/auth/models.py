from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.auth.enums import UserRole
from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from backend.db.types import GUID


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Registered user capable of authenticating with the system."""

    __tablename__ = "auth_users"
    __table_args__ = (UniqueConstraint("email", name="uq_auth_users_email"),)

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="auth_user_role", native_enum=False),
        default=UserRole.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    verification_tokens: Mapped[list[VerificationToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Issued refresh tokens allowing clients to rotate credentials."""

    __tablename__ = "auth_user_sessions"
    __table_args__ = (
        Index("ix_auth_user_sessions_user_id", "user_id"),
        Index("ix_auth_user_sessions_expires_at", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class VerificationToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Verification tokens issued during registration workflows."""

    __tablename__ = "auth_verification_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_verification_tokens_token_hash"),
        Index("ix_auth_verification_tokens_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="verification_tokens")
