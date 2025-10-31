"""Telegram bot package exposing routers and services."""

from .commands import BOT_COMMANDS, get_bot_commands, setup_bot_commands
from .config import BackendConfig
from .fsm import GenerationStates
from .handlers import CoreCommandHandlers, GenerationHandlers, create_bot_router
from .services import BackendClient, GenerationService

__all__ = (
    "BackendClient",
    "BackendConfig",
    "BOT_COMMANDS",
    "CoreCommandHandlers",
    "GenerationHandlers",
    "GenerationService",
    "GenerationStates",
    "create_bot_router",
    "get_bot_commands",
    "setup_bot_commands",
)
