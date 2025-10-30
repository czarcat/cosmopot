from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Update

from bot.runtime import BotRuntime


@pytest.mark.asyncio
async def test_start_command_authenticates_and_persists_state(bot_settings, fake_redis) -> None:
    async def backend_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "access_token": "token-abcdef-123456",
                "token_type": "bearer",
                "expires_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    transport = httpx.MockTransport(backend_handler)
    async with httpx.AsyncClient(transport=transport, base_url=str(bot_settings.backend_base_url)) as client:
        runtime = BotRuntime(bot_settings, http_client=client, redis=fake_redis)
        await runtime.startup()
        try:
            assert runtime.bot is not None and runtime.dispatcher is not None

            runtime.bot.send_message = AsyncMock()  # type: ignore[assignment]

            update = Update.model_validate(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "date": int(datetime.now(timezone.utc).timestamp()),
                        "chat": {"id": 100, "type": "private"},
                        "from": {"id": 55, "is_bot": False, "first_name": "Ada"},
                        "text": "/start",
                        "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
                    },
                }
            )

            await runtime.dispatcher.feed_update(runtime.bot, update)

            runtime.bot.send_message.assert_awaited()

            key = StorageKey(bot_id=runtime.bot.id or 0, chat_id=100, user_id=55)
            data = await runtime.dispatcher.storage.get_data(key)  # type: ignore[arg-type]
            assert data["access_token"] == "token-abcdef-123456"
        finally:
            await runtime.shutdown()
