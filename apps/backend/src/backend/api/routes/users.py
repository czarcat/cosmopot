from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies.users import (
    get_current_user,
    get_user_from_path,
)
from backend.api.schemas.users import (
    BalanceAdjustmentRequest,
    BalanceResponse,
    GDPRRequestResponse,
    QuotaSummary,
    RoleUpdateRequest,
    SessionResponse,
    SessionStatus,
    SubscriptionSummary,
    UserProfilePayload,
    UserProfileResponse,
    UserResponse,
)
from backend.db.dependencies import get_db_session
from user_service.enums import UserRole
from user_service.models import Subscription, User, UserProfile, UserSession
from user_service.repository import (
    adjust_user_balance,
    create_profile,
    get_profile_by_user_id,
    get_user_with_related,
    update_profile,
    update_user,
)
from user_service.schemas import UserProfileCreate, UserProfileUpdate, UserUpdate

router = APIRouter(prefix="/api/v1/users", tags=["users"])
logger = structlog.get_logger(__name__)

_QUOTA_PRESETS: dict[str, int] = {
    "free": 500,
    "basic": 2_000,
    "premium": 10_000,
    "enterprise": 50_000,
}


def _normalised_plan(subscription: Subscription | None) -> str:
    if subscription is None:
        return "free"
    level = (subscription.level or subscription.name or "free").strip()
    return level.lower() or "free"


def _quota_summary(subscription: Subscription | None, balance: Decimal) -> QuotaSummary:
    plan_key = _normalised_plan(subscription)
    monthly_allocation = _QUOTA_PRESETS.get(plan_key, 5_000)
    requires_top_up = balance <= Decimal("0")
    remaining_allocation = monthly_allocation if not requires_top_up else 0
    plan_label = (
        subscription.name if subscription and subscription.name else plan_key.title()
    )

    return QuotaSummary(
        plan=plan_label,
        monthly_allocation=monthly_allocation,
        remaining_allocation=remaining_allocation,
        requires_top_up=requires_top_up,
    )


def _session_status(session: UserSession) -> SessionStatus:
    now = datetime.now(UTC)
    if session.revoked_at is not None:
        return SessionStatus.REVOKED
    if session.ended_at is not None or session.expires_at <= now:
        return SessionStatus.EXPIRED
    return SessionStatus.ACTIVE


def _build_session_payload(sessions: Sequence[UserSession]) -> list[SessionResponse]:
    ordered = sorted(sessions, key=lambda item: item.created_at, reverse=True)
    return [
        SessionResponse(
            id=session.id,
            session_token=session.session_token,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
            expires_at=session.expires_at,
            created_at=session.created_at,
            revoked_at=session.revoked_at,
            ended_at=session.ended_at,
            status=_session_status(session),
        )
        for session in ordered
    ]


def _build_profile_payload(profile: UserProfile | None) -> UserProfileResponse | None:
    if profile is None:
        return None
    return UserProfileResponse(
        id=profile.id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        telegram_id=profile.telegram_id,
        phone_number=profile.phone_number,
        country=profile.country,
        city=profile.city,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        deleted_at=profile.deleted_at,
    )


def _build_user_payload(
    user: User, *, include_sessions: Iterable[UserSession]
) -> UserResponse:
    subscription_summary = (
        SubscriptionSummary.model_validate(user.subscription)
        if user.subscription is not None
        else None
    )
    quotas = _quota_summary(user.subscription, user.balance or Decimal("0"))
    sessions_payload = _build_session_payload(list(include_sessions))
    profile_payload = _build_profile_payload(user.profile)

    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        balance=user.balance,
        is_active=user.is_active,
        subscription=subscription_summary,
        quotas=quotas,
        profile=profile_payload,
        sessions=sessions_payload,
    )


def _gdpr_response(operation: str) -> GDPRRequestResponse:
    now = datetime.now(UTC)
    reference = f"{operation}-{uuid4()}"
    note = (
        "Operation queued for downstream security workflow. "
        "No immediate action is performed in this service."
    )
    return GDPRRequestResponse(
        status="scheduled",
        requested_at=now,
        reference=reference,
        note=note,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Retrieve the authenticated user's profile and account information",
)
async def read_current_user(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    user = await get_user_with_related(session, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return _build_user_payload(user, include_sessions=user.sessions or [])


@router.patch(
    "/me/profile",
    response_model=UserProfileResponse,
    summary="Create or update the authenticated user's profile information",
)
async def upsert_profile(
    payload: UserProfilePayload,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No changes supplied"
        )

    profile = await get_profile_by_user_id(session, current_user.id)

    try:
        if profile is None:
            create_schema = UserProfileCreate(user_id=current_user.id, **update_data)
            profile = await create_profile(session, create_schema)
        else:
            update_schema = UserProfileUpdate(**update_data)
            profile = await update_profile(session, profile, update_schema)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        logger.warning(
            "profile_update_conflict", user_id=current_user.id, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile update violates uniqueness constraints",
        ) from exc

    await session.refresh(profile)
    return _build_profile_payload(profile)


@router.get(
    "/me/balance",
    response_model=BalanceResponse,
    summary="Return the authenticated user's balance and quota placeholders",
)
async def read_balance(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> BalanceResponse:
    user = await get_user_with_related(session, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    quotas = _quota_summary(user.subscription, user.balance or Decimal("0"))
    return BalanceResponse(balance=user.balance, quotas=quotas)


@router.post(
    "/{user_id}/balance/adjust",
    response_model=BalanceResponse,
    summary="Adjust a user's balance within a guarded transaction",
)
async def adjust_balance(
    payload: BalanceAdjustmentRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    target_user: User = Depends(get_user_from_path),
) -> BalanceResponse:
    is_self_adjustment = target_user.id == current_user.id
    if not is_self_adjustment and current_user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrators only"
        )

    if payload.delta == Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Delta must be non-zero"
        )

    try:
        new_balance = await adjust_user_balance(session, target_user.id, payload.delta)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if detail == "user not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc

    await session.refresh(target_user)
    quotas = _quota_summary(target_user.subscription, new_balance)

    logger.info(
        "balance_adjusted",
        actor_id=current_user.id,
        target_id=target_user.id,
        delta=str(payload.delta),
        resulting_balance=str(new_balance),
        reason=payload.reason,
    )

    return BalanceResponse(balance=new_balance, quotas=quotas)


@router.post(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Update a user's role (administrator only)",
)
async def update_role(
    payload: RoleUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    target_user: User = Depends(get_user_from_path),
) -> UserResponse:
    if current_user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrators only"
        )

    update_schema = UserUpdate(role=payload.role)
    await update_user(session, target_user, update_schema)
    await session.commit()

    updated_user = await get_user_with_related(session, target_user.id)
    if updated_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    logger.info(
        "role_updated",
        actor_id=current_user.id,
        target_id=updated_user.id,
        new_role=str(updated_user.role),
    )

    return _build_user_payload(
        updated_user, include_sessions=updated_user.sessions or []
    )


@router.get(
    "/me/sessions",
    response_model=list[SessionResponse],
    summary="List authentication sessions for the authenticated user",
)
async def list_sessions(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[SessionResponse]:
    user = await get_user_with_related(session, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return _build_session_payload(user.sessions or [])


@router.delete(
    "/me/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Terminate an active session for the authenticated user",
)
async def terminate_session(
    session_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    stmt = select(UserSession).where(UserSession.id == session_id)
    result = await session.execute(stmt)
    user_session = result.scalar_one_or_none()
    if user_session is None or user_session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    now = datetime.now(UTC)
    if user_session.revoked_at is None:
        user_session.revoked_at = now
    user_session.ended_at = now

    await session.flush()
    await session.commit()
    await session.refresh(user_session)

    logger.info(
        "session_revoked",
        user_id=current_user.id,
        session_id=user_session.id,
        token=user_session.session_token,
    )

    return _build_session_payload([user_session])[0]


@router.post(
    "/me/data-export",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GDPRRequestResponse,
    summary="Schedule a GDPR-compliant data export (placeholder)",
)
async def schedule_data_export(
    _current_user: User = Depends(get_current_user),
) -> GDPRRequestResponse:
    return _gdpr_response("export")


@router.post(
    "/me/data-delete",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GDPRRequestResponse,
    summary="Schedule a GDPR-compliant account deletion (placeholder)",
)
async def schedule_data_delete(
    _current_user: User = Depends(get_current_user),
) -> GDPRRequestResponse:
    return _gdpr_response("delete")
