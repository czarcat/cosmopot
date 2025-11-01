from __future__ import annotations

import asyncio
from typing import Any, Protocol

from yookassa import Configuration
from yookassa import Payment as YooPayment

try:  # pragma: no cover - compatibility layer for SDK import changes
    from yookassa.exceptions import YooKassaError
except ImportError:  # pragma: no cover
    from yookassa.domain.exceptions import ApiError as YooKassaError

from .exceptions import PaymentGatewayError


class PaymentGateway(Protocol):
    """Protocol describing the operations required from a payment provider."""

    async def create_payment(
        self, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        """Create a payment with the provider and return its serialised response."""


class YooKassaGateway:
    """Thin asynchronous wrapper around the official YooKassa SDK."""

    def __init__(self, *, shop_id: str, secret_key: str) -> None:
        if not shop_id:
            raise ValueError("shop_id must be provided")
        if not secret_key:
            raise ValueError("secret_key must be provided")
        self._shop_id = str(shop_id)
        self._secret_key = secret_key
        Configuration.configure(self._shop_id, self._secret_key)

    async def create_payment(
        self, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            Configuration.configure(self._shop_id, self._secret_key)
            result = YooPayment.create(payload, idempotency_key)
            if isinstance(result, dict):
                return result
            if hasattr(result, "to_dict"):
                return result.to_dict()
            raise PaymentGatewayError("Unexpected YooKassa response type")

        try:
            return await asyncio.to_thread(_call)
        except YooKassaError as exc:
            raise PaymentGatewayError(str(exc)) from exc
