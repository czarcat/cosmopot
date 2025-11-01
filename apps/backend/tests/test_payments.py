from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.payments.dependencies import (
    get_payment_service,
    reset_payment_dependencies,
)
from backend.payments.enums import PaymentStatus
from backend.payments.models import Payment
from backend.payments.service import PaymentService
from user_service.models import SubscriptionPlan, User


@dataclass(slots=True)
class StubGateway:
    """Deterministic gateway stub returning queued responses."""

    responses: list[dict[str, Any]]

    def __post_init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []

    async def create_payment(
        self, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        self.calls.append((payload, idempotency_key))
        if self.responses:
            response = self.responses.pop(0)
        else:
            response = {
                "id": f"pay-{uuid4().hex}",
                "status": "pending",
                "confirmation": {"confirmation_url": "https://payments.test/confirm"},
            }
        return json.loads(json.dumps(response))


class StubNotifier:
    def __init__(self) -> None:
        self.notifications: list[dict[str, Any]] = []

    async def notify(
        self,
        user: User,
        payment: Payment,
        status: PaymentStatus,
        context: dict[str, Any],
    ) -> None:
        self.notifications.append(
            {
                "user_id": user.id,
                "payment_id": str(payment.id),
                "status": status,
                "context": context,
            }
        )


async def _persist(
    session_factory: async_sessionmaker[AsyncSession], instance: Any
) -> Any:
    async with session_factory() as session:
        session.add(instance)
        await session.commit()
        await session.refresh(instance)
        return instance


async def create_subscription_plan(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "Basic",
    level: str = "basic",
    monthly_cost: Decimal = Decimal("9.99"),
) -> SubscriptionPlan:
    plan = SubscriptionPlan(name=name, level=level, monthly_cost=monthly_cost)
    return await _persist(session_factory, plan)


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    balance: Decimal = Decimal("0.00"),
    subscription_plan: SubscriptionPlan | None = None,
) -> User:
    user = User(
        email=f"user-{uuid4().hex}@example.com",
        hashed_password="hashed",
        balance=balance,
    )
    if subscription_plan is not None:
        user.subscription_id = subscription_plan.id
    return await _persist(session_factory, user)


@pytest.fixture()
async def payment_dependencies(app):  # type: ignore[annotation-unchecked]
    reset_payment_dependencies()
    gateway = StubGateway(
        responses=[
            {
                "id": "pay-test-1",
                "status": "pending",
                "confirmation": {"confirmation_url": "https://payments.test/confirm"},
            }
        ]
    )
    notifier = StubNotifier()
    service = PaymentService(
        settings=app.state.settings, gateway=gateway, notifier=notifier
    )
    app.dependency_overrides[get_payment_service] = lambda: service
    try:
        yield gateway, notifier, service
    finally:
        app.dependency_overrides.pop(get_payment_service, None)
        reset_payment_dependencies()


@pytest.mark.asyncio
async def test_create_payment_persists_record(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    payment_dependencies,
) -> None:
    gateway, notifier, _service = payment_dependencies
    subscription_plan = await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    response = await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["provider_payment_id"] == "pay-test-1"
    assert payload["confirmation_url"] == "https://payments.test/confirm"
    assert payload["status"] == PaymentStatus.PENDING.value

    async with session_factory() as session:
        db_payment = await session.get(Payment, payload["id"])
        assert db_payment is not None
        assert db_payment.user_id == user.id
        assert db_payment.subscription_id == subscription_plan.id
        assert db_payment.status is PaymentStatus.PENDING
        assert db_payment.metadata["plan_code"] == "basic"

    assert len(gateway.calls) == 1
    request_payload, idempotency_key = gateway.calls[0]
    assert request_payload["amount"]["value"] == "9.99"
    assert idempotency_key.startswith(str(user.id))
    assert notifier.notifications == []


@pytest.mark.asyncio
async def test_create_payment_respects_idempotency_key(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    payment_dependencies,
) -> None:
    gateway, _notifier, _service = payment_dependencies
    await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    idempotency_key = "test-idempotency-12345"
    for _ in range(2):
        response = await async_client.post(
            "/api/v1/payments/create",
            headers={"X-User-Id": str(user.id)},
            json={
                "plan_code": "basic",
                "success_url": "https://example.com/success",
                "idempotency_key": idempotency_key,
            },
        )
        assert response.status_code == 201

    assert len(gateway.calls) == 1

    async with session_factory() as session:
        payments = (await session.execute(Payment.__table__.select())).all()
        assert len(payments) == 1


@pytest.mark.asyncio
async def test_webhook_success_updates_subscription_and_balance(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    payment_dependencies,
) -> None:
    gateway, notifier, service = payment_dependencies
    subscription_plan = await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    # Initiate payment to create record in DB
    create_response = await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
        },
    )
    payment_payload = create_response.json()

    webhook_payload = {
        "event": "payment.succeeded",
        "object": {
            "id": "pay-test-1",
            "status": "succeeded",
        },
    }
    secret = "test-webhook-secret"
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    response = await async_client.post(
        "/api/v1/webhooks/yukassa",
        content=raw_body,
        headers={"Content-Hmac": f"sha256={signature}"},
    )
    assert response.status_code == 202

    async with session_factory() as session:
        payment = await session.get(Payment, payment_payload["id"])
        assert payment is not None
        assert payment.status is PaymentStatus.SUCCEEDED
        assert payment.captured_at is not None

        refreshed_user = await session.get(User, user.id)
        assert refreshed_user is not None
        assert refreshed_user.subscription_id == subscription_plan.id
        assert refreshed_user.balance == Decimal("9.99")

    assert notifier.notifications
    notification = notifier.notifications[-1]
    assert notification["status"] is PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_webhook_failure_marks_payment(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    payment_dependencies,
) -> None:
    gateway, notifier, _service = payment_dependencies
    await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
        },
    )

    payload = {
        "event": "payment.canceled",
        "object": {
            "id": "pay-test-1",
            "status": "canceled",
            "cancellation_details": {"reason": "expired"},
        },
    }
    secret = "test-webhook-secret"
    raw_body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    response = await async_client.post(
        "/api/v1/webhooks/yukassa",
        content=raw_body,
        headers={"Content-Hmac": f"sha256={signature}"},
    )
    assert response.status_code == 202

    async with session_factory() as session:
        result = await session.execute(select(Payment))
        payment = result.scalars().first()
        assert payment is not None
        assert payment.status is PaymentStatus.CANCELED
        assert payment.failure_reason == "expired"

    assert notifier.notifications
    assert notifier.notifications[-1]["status"] is PaymentStatus.CANCELED


@pytest.mark.asyncio
async def test_webhook_invalid_signature_rejected(
    async_client: AsyncClient,
    payment_dependencies,
) -> None:
    payload = {"event": "payment.succeeded", "object": {"id": "unknown"}}
    response = await async_client.post(
        "/api/v1/webhooks/yukassa",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Hmac": "sha256=invalid"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_missing_payment_returns_404(
    async_client: AsyncClient,
    payment_dependencies,
) -> None:
    secret = "test-webhook-secret"
    payload = {
        "event": "payment.succeeded",
        "object": {
            "id": "pay-missing",
            "status": "succeeded",
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    response = await async_client.post(
        "/api/v1/webhooks/yukassa",
        content=raw_body,
        headers={"Content-Hmac": f"sha256={signature}"},
    )
    assert response.status_code == 404
