from __future__ import annotations

from fastapi import Depends, HTTPException, status

from backend.core.config import Settings, get_settings
from backend.payments.gateway import PaymentGateway, YooKassaGateway
from backend.payments.notifications import LoggingPaymentNotifier, PaymentNotifier
from backend.payments.service import PaymentService

_GATEWAY: PaymentGateway | None = None
_NOTIFIER: PaymentNotifier | None = None


def get_payment_gateway(settings: Settings = Depends(get_settings)) -> PaymentGateway:
    global _GATEWAY
    if _GATEWAY is not None:
        return _GATEWAY

    yookassa = settings.yookassa
    if yookassa.shop_id is None or yookassa.secret_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YooKassa integration is not configured",
        )

    _GATEWAY = YooKassaGateway(
        shop_id=str(yookassa.shop_id),
        secret_key=yookassa.secret_key.get_secret_value(),
    )
    return _GATEWAY


def get_payment_notifier() -> PaymentNotifier:
    global _NOTIFIER
    if _NOTIFIER is None:
        _NOTIFIER = LoggingPaymentNotifier()
    return _NOTIFIER


def get_payment_service(
    settings: Settings = Depends(get_settings),
    gateway: PaymentGateway = Depends(get_payment_gateway),
    notifier: PaymentNotifier = Depends(get_payment_notifier),
) -> PaymentService:
    return PaymentService(settings=settings, gateway=gateway, notifier=notifier)


def reset_payment_dependencies() -> None:
    """Reset cached singletons to allow reconfiguration during tests."""

    global _GATEWAY, _NOTIFIER
    _GATEWAY = None
    _NOTIFIER = None
