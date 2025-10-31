from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies.users import get_current_user
from backend.api.schemas.payments import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentWebhookAck,
)
from backend.auth.dependencies import get_rate_limiter
from backend.auth.rate_limiter import RateLimiter
from backend.db.dependencies import get_db_session
from backend.payments.dependencies import get_payment_service
from backend.payments.exceptions import (
    PaymentConfigurationError,
    PaymentGatewayError,
    PaymentNotFoundError,
    PaymentPlanNotFoundError,
    PaymentSignatureError,
)
from backend.payments.service import PaymentService
from user_service.models import User

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def _map_payment_to_response(payment) -> PaymentCreateResponse:  # type: ignore[no-untyped-def]
    return PaymentCreateResponse(
        id=payment.id,
        provider_payment_id=payment.provider_payment_id,
        status=payment.status,
        confirmation_url=payment.confirmation_url,
        amount=payment.amount,
        currency=payment.currency,
    )


@router.post(
    "/create",
    response_model=PaymentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a YooKassa payment for a subscription plan",
)
async def create_payment(
    payload: PaymentCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentCreateResponse:
    await rate_limiter.check("payments:create", str(current_user.id))

    try:
        async with session.begin():
            payment = await payment_service.create_payment(
                session, current_user, payload.to_domain()
            )
    except PaymentPlanNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PaymentConfigurationError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except PaymentGatewayError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    await session.refresh(payment)
    return _map_payment_to_response(payment)


@router.post(
    "/webhooks/yukassa",
    response_model=PaymentWebhookAck,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Handle YooKassa webhook callbacks",
)
async def handle_yookassa_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentWebhookAck:
    raw_body = await request.body()
    signature = request.headers.get("Content-Hmac")

    try:
        payment_service.verify_webhook_signature(signature, raw_body)
    except PaymentSignatureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PaymentConfigurationError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload"
        ) from exc

    try:
        async with session.begin():
            await payment_service.process_webhook(session, payload)
    except PaymentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return PaymentWebhookAck()
