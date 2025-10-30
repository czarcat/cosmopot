from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Roles available to a user account."""

    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"


class SubscriptionTier(StrEnum):
    """Supported billing tiers for subscriptions."""

    FREE = "free"
    STANDARD = "standard"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(StrEnum):
    """Lifecycle states for a subscription instance."""

    TRIALING = "trialing"
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


class PaymentStatus(StrEnum):
    """Possible settlement states for a payment record."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class TransactionType(StrEnum):
    """Ledger classification for monetary transactions."""

    CHARGE = "charge"
    REFUND = "refund"
    CREDIT = "credit"


class PromptSource(StrEnum):
    """Origin for prompt templates."""

    SYSTEM = "system"
    USER = "user"
    EXTERNAL = "external"


class GenerationTaskStatus(StrEnum):
    """Lifecycle states for content generation tasks."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class GenerationTaskSource(StrEnum):
    """Indicates how a generation task was initiated."""

    API = "api"
    SCHEDULER = "scheduler"
    WORKFLOW = "workflow"
