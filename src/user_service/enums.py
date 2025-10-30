from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Roles available to a user account."""

    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"
