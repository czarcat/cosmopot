from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums import (
    PaymentStatus,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
    UserRole,
)


class Base(DeclarativeBase):
    """Base class for declarative models."""


class SubscriptionPlan(Base):
    """Represents an available subscription plan template."""

    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    monthly_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    users: Mapped[List["User"]] = relationship(
        back_populates="subscription_plan", passive_deletes=True
    )


class User(Base):
    """Stores core authentication and account information for a person."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        nullable=False,
        default=UserRole.USER,
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0"), default=Decimal("0")
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    profile: Mapped["UserProfile"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[List["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    subscription_plan: Mapped[Optional[SubscriptionPlan]] = relationship(
        back_populates="users"
    )
    subscriptions: Mapped[List["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    payments: Mapped[List["Payment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


Index("ix_users_role", User.role)


class Subscription(Base):
    """Tracks the lifecycle of a user's billing subscription."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("quota_limit >= 0", name="ck_subscriptions_quota_limit_positive"),
        CheckConstraint("quota_used >= 0", name="ck_subscriptions_quota_used_positive"),
        CheckConstraint(
            "quota_used <= quota_limit", name="ck_subscriptions_quota_within_limit"
        ),
        CheckConstraint(
            "current_period_end > current_period_start",
            name="ck_subscriptions_period_order",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier, name="subscription_tier", native_enum=False),
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
        server_default=text("'active'"),
    )
    auto_renew: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    quota_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    quota_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    provider_subscription_id: Mapped[Optional[str]] = mapped_column(String(120))
    provider_data: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    metadata: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="subscriptions")
    history: Mapped[List["SubscriptionHistory"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", passive_deletes=True
    )
    payments: Mapped[List["Payment"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", passive_deletes=True
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", passive_deletes=True
    )


Index("ix_subscriptions_user_status", Subscription.user_id, Subscription.status)
Index(
    "uq_subscriptions_user_active",
    Subscription.user_id,
    unique=True,
    sqlite_where=text("status IN ('active', 'trialing')"),
    postgresql_where=text("status IN ('active', 'trialing')"),
)


class SubscriptionHistory(Base):
    """Immutable snapshots capturing subscription changes."""

    __tablename__ = "subscription_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier, name="subscription_history_tier", native_enum=False),
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(
            SubscriptionStatus,
            name="subscription_history_status",
            native_enum=False,
        ),
        nullable=False,
    )
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quota_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_used: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_subscription_id: Mapped[Optional[str]] = mapped_column(String(120))
    provider_data: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    metadata: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    subscription: Mapped[Subscription] = relationship(back_populates="history")


Index(
    "ix_subscription_history_subscription_id",
    SubscriptionHistory.subscription_id,
)


class Payment(Base):
    """Represents a monetary settlement attempt for a subscription."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        nullable=False,
        default=PaymentStatus.COMPLETED,
        server_default=text("'completed'"),
    )
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(120))
    provider_data: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    metadata: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    subscription: Mapped[Optional[Subscription]] = relationship(back_populates="payments")
    user: Mapped[User] = relationship(back_populates="payments")
    transactions: Mapped[List["Transaction"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan", passive_deletes=True
    )


Index("ix_payments_user_id", Payment.user_id)
Index("ix_payments_subscription_id", Payment.subscription_id)
Index("ix_payments_status", Payment.status)
Index(
    "uq_payments_provider_payment_id",
    Payment.provider_payment_id,
    unique=True,
    sqlite_where=text("provider_payment_id IS NOT NULL"),
    postgresql_where=text("provider_payment_id IS NOT NULL"),
)


class Transaction(Base):
    """Ledger line item tied to a payment and optionally a subscription."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=False),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(String(255))
    provider_reference: Mapped[Optional[str]] = mapped_column(String(120))
    metadata: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    payment: Mapped[Payment] = relationship(back_populates="transactions")
    subscription: Mapped[Optional[Subscription]] = relationship(
        back_populates="transactions"
    )
    user: Mapped[User] = relationship(back_populates="transactions")


Index("ix_transactions_payment_id", Transaction.payment_id)
Index("ix_transactions_subscription_id", Transaction.subscription_id)
Index("ix_transactions_user_id", Transaction.user_id)
Index("ix_transactions_type", Transaction.type)
Index(
    "uq_transactions_provider_reference",
    Transaction.provider_reference,
    unique=True,
    sqlite_where=text("provider_reference IS NOT NULL"),
    postgresql_where=text("provider_reference IS NOT NULL"),
)
