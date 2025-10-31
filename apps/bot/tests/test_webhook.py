from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram.types import Update
from fastapi import FastAPI

from backend.api.routes.bot import router as bot_router
from bot.runtime import BotRuntime


@pytest.mark.asyncio
async def test_webhook_route_dispatches_update(bot_settings, fake_redis) -> None:
    async def backend_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "access_token": "token-xyz",
                "token_type": "bearer",
                "expires_at": datetime.now(UTC).isoformat(),
            },
        )

    transport = httpx.MockTransport(backend_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url=str(bot_settings.backend_base_url)
    ) as client:
        runtime = BotRuntime(bot_settings, http_client=client, redis=fake_redis)
        await runtime.startup()
        try:
            assert runtime.bot is not None and runtime.dispatcher is not None
            runtime.bot.send_message = AsyncMock()  # type: ignore[assignment]

            app = FastAPI()
            app.state.settings = bot_settings
            app.state.bot_runtime = runtime
            app.include_router(bot_router)

            update = Update.model_validate(
                {
                    "update_id": 77,
                    "message": {
                        "message_id": 10,
                        "date": int(datetime.now(UTC).timestamp()),
                        "chat": {"id": 200, "type": "private"},
                        "from": {"id": 88, "is_bot": False, "first_name": "Grace"},
                        "text": "/start",
                        "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
                    },
                }
            )

            headers = {
                "X-Telegram-Bot-Api-Secret-Token": bot_settings.telegram_webhook_secret_token.get_secret_value()
            }

            async with httpx.AsyncClient(
                app=app, base_url="http://testserver"
            ) as test_client:
                response = await test_client.post(
                    "/api/v1/bot/webhook",
                    json=update.model_dump(mode="json"),
                    headers=headers,
                )

            assert response.status_code == httpx.codes.NO_CONTENT
            runtime.bot.send_message.assert_awaited()
        finally:
            await runtime.shutdown()
