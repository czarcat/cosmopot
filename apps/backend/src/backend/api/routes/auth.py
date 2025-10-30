from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import Settings
from backend.db.dependencies import get_db_session
from backend.services import (
    TelegramAuthError,
    TelegramAuthInactiveUserError,
    TelegramAuthReplayError,
    TelegramAuthService,
    TelegramAuthSignatureError,
    TelegramLoginPayload,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime

    model_config = ConfigDict(json_encoders={datetime: lambda value: value.isoformat()})


@router.post("/telegram", response_model=TelegramAuthResponse)
async def telegram_authenticate(
    request: Request,
    payload: TelegramLoginPayload,
    session: AsyncSession = Depends(get_db_session),
) -> TelegramAuthResponse:
    settings: Settings = request.app.state.settings

    if settings.telegram_bot_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram authentication is not configured",
        )

    service = TelegramAuthService(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        login_ttl_seconds=settings.telegram_login_ttl_seconds,
        jwt_secret=settings.jwt_secret_key.get_secret_value(),
        jwt_algorithm=settings.jwt_algorithm,
        access_token_ttl_seconds=settings.jwt_access_ttl_seconds,
    )

    try:
        result = await service.authenticate(
            session,
            payload,
            user_agent=request.headers.get("user-agent"),
            ip_address=_extract_client_ip(request),
        )
        await session.commit()
    except TelegramAuthSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except TelegramAuthReplayError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except TelegramAuthInactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except TelegramAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return TelegramAuthResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_at=result.expires_at,
    )


def _extract_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client is not None:
        return request.client.host

    return None
