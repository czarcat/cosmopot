from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import PaymentPlan, Settings
from backend.payments.enums import PaymentEventType, PaymentStatus
from backend.payments.exceptions import (
    PaymentConfigurationError,
    PaymentGatewayError,
    PaymentNotFoundError,
    PaymentPlanNotFoundError,
    PaymentSignatureError,
)
from backend.payments.gateway import PaymentGateway
from backend.payments.models import Payment, PaymentEvent
from backend.payments.notifications import LoggingPaymentNotifier, PaymentNotifier
from user_service.models import Subscription, User


@dataclass(slots=True)
class PaymentRequest:
    """Input payload required to initiate a payment."""

    plan_code: str
    success_url: str
    cancel_url: str | None = None
    idempotency_key: str | None = None


class PaymentService:
    """Coordinates payment creation, webhook processing, and user notifications."""

    def __init__(
        self,
        *,
        settings: Settings,
        gateway: PaymentGateway,
        notifier: PaymentNotifier | None = None,
    ) -> None:
        self._settings = settings
        self._gateway = gateway
        self._notifier = notifier or LoggingPaymentNotifier()
        self._logger = structlog.get_logger(__name__)

    async def create_payment(self, session: AsyncSession, user: User, request: PaymentRequest) -> Payment:
        plan = self._resolve_plan(request.plan_code)
        subscription = await self._get_subscription(session, plan.subscription_level)

        currency = plan.currency or self._settings.payments.default_currency
        amount = plan.amount.quantize(Decimal("0.01"))

        idempotency_key = request.idempotency_key or self._generate_idempotency_key(user.id)
        existing = await self._find_payment(session, user.id, idempotency_key)
        if existing is not None:
            self._logger.info(
                "payment_idempotency_hit",
                user_id=user.id,
                payment_id=str(existing.id),
                idempotency_key=idempotency_key,
            )
            return existing

        provider_payload = self._build_provider_payload(
            amount=amount,
            currency=currency,
            plan_code=plan.code,
            description=plan.description,
            user=user,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )

        provider_response = await self._gateway.create_payment(provider_payload, idempotency_key=idempotency_key)
        provider_payment_id = provider_response.get("id")
        if not provider_payment_id:
            raise PaymentGatewayError("YooKassa response missing payment identifier")

        status = self._map_provider_status(provider_response.get("status"))
        confirmation_url = self._extract_confirmation_url(provider_response)

        payment = Payment(
            user_id=user.id,
            subscription_id=subscription.id,
            provider_payment_id=provider_payment_id,
            idempotency_key=idempotency_key,
            status=status,
            amount=amount,
            currency=currency,
            confirmation_url=confirmation_url,
            description=provider_payload.get("description"),
            metadata=self._build_metadata(
                plan_code=plan.code,
                plan_level=plan.subscription_level,
                success_url=request.success_url,
                cancel_url=request.cancel_url,
                provider_payload=provider_payload,
                provider_response=provider_response,
            ),
        )
        session.add(payment)

        session.add(
            PaymentEvent(
                payment=payment,
                event_type=PaymentEventType.REQUEST,
                provider_status=status,
                data={
                    "payload": provider_payload,
                    "response": provider_response,
                },
                note="Payment initiated",
            )
        )

        await session.flush()
        await session.refresh(payment)
        return payment

    async def process_webhook(self, session: AsyncSession, payload: dict[str, Any]) -> Payment:
        event_name = payload.get("event")
        provider_object = payload.get("object") or {}
        provider_payment_id = provider_object.get("id")
        if not provider_payment_id:
            raise PaymentNotFoundError("Webhook payload missing provider payment id")

        payment = await self._lock_payment_by_provider_id(session, provider_payment_id)
        if payment is None:
            raise PaymentNotFoundError(f"Payment with provider id '{provider_payment_id}' not found")

        new_status = self._map_webhook_status(event_name, provider_object.get("status"))
        previous_status = payment.status

        session.add(
            PaymentEvent(
                payment=payment,
                event_type=PaymentEventType.WEBHOOK,
                provider_status=new_status,
                data=payload,
                note=f"Webhook event {event_name or 'unknown'}",
            )
        )

        metadata_updates: dict[str, Any] = {
            "last_webhook_event": event_name,
            "provider_status": provider_object.get("status"),
        }

        if new_status is not payment.status:
            payment.status = new_status
            now = self._now()
            if new_status is PaymentStatus.SUCCEEDED and previous_status is not PaymentStatus.SUCCEEDED:
                payment.captured_at = now
                user = await self._activate_subscription(session, payment)
                metadata_updates["activated_at"] = now.isoformat()
                await self._notify(user, payment, new_status, payload)
            elif new_status in {PaymentStatus.CANCELED, PaymentStatus.FAILED, PaymentStatus.REFUNDED}:
                payment.canceled_at = now
                cancellation = provider_object.get("cancellation_details") or {}
                failure = provider_object.get("failure") or {}
                payment.failure_reason = cancellation.get("reason") or failure.get("description")
                metadata_updates["cancellation_details"] = cancellation or failure
                await self._notify(await session.get(User, payment.user_id), payment, new_status, payload)
            else:
                await self._notify(await session.get(User, payment.user_id), payment, new_status, payload)

        confirmation_url = self._extract_confirmation_url(provider_object)
        if confirmation_url:
            payment.confirmation_url = confirmation_url

        self._apply_metadata_updates(payment, metadata_updates)
        await session.flush()

        return payment

    def verify_webhook_signature(self, signature_header: str | None, raw_body: bytes) -> None:
        if not signature_header:
            raise PaymentSignatureError("Missing Content-Hmac header")

        secret = self._settings.yookassa.webhook_secret
        if secret is None:
            raise PaymentConfigurationError("Webhook secret is not configured")

        algorithm, _, provided = signature_header.partition("=")
        if algorithm.lower() != "sha256" or not provided:
            raise PaymentSignatureError("Unsupported webhook signature format")

        expected = hmac.new(
            secret.get_secret_value().encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, provided.strip()):
            raise PaymentSignatureError("Webhook signature mismatch")

    async def _notify(
        self,
        user: User | None,
        payment: Payment,
        status: PaymentStatus,
        context: dict[str, Any],
    ) -> None:
        if user is None:
            self._logger.warning(
                "payment_notify_user_missing",
                user_id=payment.user_id,
                payment_id=str(payment.id),
                status=status.value,
            )
            return
        await self._notifier.notify(user, payment, status, context)

    async def _activate_subscription(self, session: AsyncSession, payment: Payment) -> User | None:
        stmt = select(User).where(User.id == payment.user_id).with_for_update()
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            self._logger.warning(
                "payment_user_missing",
                user_id=payment.user_id,
                payment_id=str(payment.id),
            )
            return None

        user.subscription_id = payment.subscription_id
        current_balance = Decimal(user.balance or Decimal("0"))
        user.balance = (current_balance + payment.amount).quantize(Decimal("0.01"))
        await session.flush()
        return user

    async def _lock_payment_by_provider_id(
        self, session: AsyncSession, provider_payment_id: str
    ) -> Payment | None:
        stmt = (
            select(Payment)
            .where(Payment.provider_payment_id == provider_payment_id)
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_subscription(self, session: AsyncSession, level: str) -> Subscription:
        stmt = select(Subscription).where(Subscription.level == level)
        result = await session.execute(stmt)
        subscription = result.scalar_one_or_none()
        if subscription is None:
            raise PaymentPlanNotFoundError(f"Subscription level '{level}' is not configured in the database")
        return subscription

    async def _find_payment(
        self, session: AsyncSession, user_id: int, idempotency_key: str
    ) -> Payment | None:
        stmt = (
            select(Payment)
            .where(
                Payment.user_id == user_id,
                Payment.idempotency_key == idempotency_key,
            )
            .order_by(Payment.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _resolve_plan(self, code: str) -> PaymentPlan:
        try:
            return self._settings.payments.get_plan(code)
        except KeyError as exc:
            raise PaymentPlanNotFoundError(f"Unknown payment plan '{code}'") from exc

    def _generate_idempotency_key(self, user_id: int) -> str:
        return f"{user_id}-{uuid.uuid4().hex}"

    def _build_provider_payload(
        self,
        *,
        amount: Decimal,
        currency: str,
        plan_code: str,
        description: str | None,
        user: User,
        success_url: str,
        cancel_url: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": success_url,
            },
            "description": description or f"Subscription upgrade '{plan_code}'",
            "metadata": {
                "user_id": user.id,
                "plan": plan_code,
                "cancel_url": cancel_url,
            },
        }
        return payload

    def _build_metadata(
        self,
        *,
        plan_code: str,
        plan_level: str,
        success_url: str,
        cancel_url: str | None,
        provider_payload: dict[str, Any],
        provider_response: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "plan_code": plan_code,
            "plan_level": plan_level,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "provider_payload": provider_payload,
            "provider_response": provider_response,
        }

    def _map_provider_status(self, status: str | None) -> PaymentStatus:
        mapping = {
            "pending": PaymentStatus.PENDING,
            "waiting_for_capture": PaymentStatus.WAITING_FOR_CAPTURE,
            "succeeded": PaymentStatus.SUCCEEDED,
            "canceled": PaymentStatus.CANCELED,
            "refunded": PaymentStatus.REFUNDED,
            "failed": PaymentStatus.FAILED,
        }
        return mapping.get((status or "").lower(), PaymentStatus.PENDING)

    def _map_webhook_status(self, event_name: str | None, status: str | None) -> PaymentStatus:
        event_mapping = {
            "payment.succeeded": PaymentStatus.SUCCEEDED,
            "payment.waiting_for_capture": PaymentStatus.WAITING_FOR_CAPTURE,
            "payment.canceled": PaymentStatus.CANCELED,
            "payment.failed": PaymentStatus.FAILED,
            "refund.succeeded": PaymentStatus.REFUNDED,
        }
        if event_name in event_mapping:
            return event_mapping[event_name]
        return self._map_provider_status(status)

    def _extract_confirmation_url(self, payload: dict[str, Any]) -> str | None:
        confirmation = payload.get("confirmation")
        if isinstance(confirmation, dict):
            return confirmation.get("confirmation_url") or confirmation.get("url")
        return None

    def _apply_metadata_updates(self, payment: Payment, updates: dict[str, Any]) -> None:
        metadata = dict(payment.metadata or {})
        metadata.update(updates)
        payment.metadata = metadata

    def _now(self) -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)
