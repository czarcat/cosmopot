from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Mapping, cast

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.db.types import GUID, JSONType

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class Base(DeclarativeBase):
    metadata: MetaData | dict[str, Any] = metadata


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4, nullable=False
    )


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class JSONDataMixin:
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONType(),
        default=dict,
        nullable=False,
    )


class MetadataAliasMixin:
    """Provide instance-level access to JSON metadata without shadowing
    Base.metadata."""

    _metadata_marker = object()
    meta_data: dict[str, Any]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        metadata_value = kwargs.pop("metadata", self._metadata_marker)
        if metadata_value is not self._metadata_marker and "meta_data" not in kwargs:
            kwargs["meta_data"] = metadata_value
        super().__init__(*args, **kwargs)

    @property
    def metadata(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.meta_data)

    @metadata.setter
    def metadata(self, value: Mapping[str, Any]) -> None:
        self.meta_data = dict(value)

    @metadata.deleter
    def metadata(self) -> None:
        del self.meta_data
