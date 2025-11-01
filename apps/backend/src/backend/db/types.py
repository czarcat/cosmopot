from __future__ import annotations

import json
import uuid
from typing import Any, cast

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator[uuid.UUID]):
    """Platform-independent GUID type.

    Uses PostgreSQL's native UUID type when available, otherwise falls back to
    a CHAR(36) representation.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return cast(TypeEngine[Any], dialect.type_descriptor(PG_UUID(as_uuid=True)))
        return cast(TypeEngine[Any], dialect.type_descriptor(CHAR(36)))

    def process_bind_param(
        self, value: uuid.UUID | None, dialect: Dialect
    ) -> Any:
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        raise TypeError("GUID values must be UUID instances")

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


JSONValue = dict[str, Any] | list[Any]


class JSONType(TypeDecorator[JSONValue]):
    """JSONB wrapper that ensures consistent behaviour across dialects."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(
        self, value: JSONValue | None, dialect: Dialect
    ) -> Any:
        if value is None:
            return value
        if isinstance(value, (dict, list)):
            return cast(JSONValue, json.loads(json.dumps(value)))
        raise TypeError("JSONType values must be dicts or lists")

    def process_result_value(
        self, value: Any, dialect: Dialect
    ) -> JSONValue | None:
        if value is None:
            return value
        if isinstance(value, (dict, list)):
            return cast(JSONValue, value)
        return cast(JSONValue, json.loads(value))
