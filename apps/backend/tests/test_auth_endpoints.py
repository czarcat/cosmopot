from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _register(async_client: AsyncClient, email: str, password: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["verification_token"]


async def _verify(async_client: AsyncClient, token: str) -> None:
    response = await async_client.post("/api/v1/auth/verify", json={"token": token})
    assert response.status_code == 200


async def _login(async_client: AsyncClient, email: str, password: str) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio()
async def test_register_verify_and_login_flow(async_client: AsyncClient) -> None:
    email = "user@example.com"
    password = "StrongPassw0rd!"

    token = await _register(async_client, email, password)

    # Login before verification should fail.
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 403

    await _verify(async_client, token)

    login_payload = await _login(async_client, email, password)
    assert login_payload["user"]["email"] == email
    assert "access_token" in login_payload
    assert "refresh_token" in login_payload

    access_token = login_payload["access_token"]

    me_response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert me_payload["email"] == email
    assert me_payload["is_verified"] is True


@pytest.mark.asyncio()
async def test_refresh_rotates_tokens(async_client: AsyncClient) -> None:
    email = "rotate@example.com"
    password = "RotatePass123!"

    token = await _register(async_client, email, password)
    await _verify(async_client, token)

    login_payload = await _login(async_client, email, password)
    original_refresh = login_payload["refresh_token"]
    original_session = login_payload["session_id"]

    refresh_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["session_id"] != original_session

    # Attempting to reuse the old refresh token should now fail.
    reuse_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert reuse_response.status_code == 401

    # New access token should authorise /me
    new_access = refreshed["access_token"]
    me_response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == email


@pytest.mark.asyncio()
async def test_logout_revokes_refresh_token(async_client: AsyncClient) -> None:
    email = "logout@example.com"
    password = "LogoutPass123!"

    token = await _register(async_client, email, password)
    await _verify(async_client, token)

    login_payload = await _login(async_client, email, password)
    refresh_token = login_payload["refresh_token"]

    logout_response = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_response.status_code == 200
    set_cookie_headers = logout_response.headers.get_list("set-cookie")
    assert any("Max-Age=0" in header for header in set_cookie_headers)

    reuse_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert reuse_response.status_code == 401


@pytest.mark.asyncio()
async def test_rate_limit_enforced_on_login(async_client: AsyncClient) -> None:
    email = "ratelimit@example.com"
    password = "RateLimitPass123!"

    token = await _register(async_client, email, password)
    await _verify(async_client, token)

    # Consume the allowed attempts with wrong passwords.
    for _ in range(5):
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong"},
        )
        assert response.status_code == 401

    blocked_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong"},
    )
    assert blocked_response.status_code == 429
    assert "Retry-After" in blocked_response.headers
