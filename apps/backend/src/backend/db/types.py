from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator[uuid.UUID]):
    """Platform-independent GUID type.

    Uses PostgreSQL's native UUID type when available, otherwise falls back to
    a CHAR(36) representation.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect):  # type: ignore[override]
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        raise TypeError("GUID values must be UUID instances")

    def process_result_value(self, value: Any, dialect):  # type: ignore[override]
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class JSONType(TypeDecorator[dict[str, Any]]):
    """JSONB wrapper that ensures consistent behaviour across dialects."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value: Any, dialect):  # type: ignore[override]
        if value is None:
            return value
        if isinstance(value, (dict, list)):
            return json.loads(json.dumps(value))
        raise TypeError("JSONType values must be dicts or lists")

    def process_result_value(self, value: Any, dialect):  # type: ignore[override]
        if value is None:
            return value
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)
