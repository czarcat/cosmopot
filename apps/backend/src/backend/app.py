from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

import backend.payments.models  # noqa: F401 - ensure models are registered with SQLAlchemy metadata
import backend.generation.models  # noqa: F401 - ensure generation models are registered
from backend.api.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from backend.api.routes import load_routers
from backend.auth.middleware import CurrentUserMiddleware
from backend.auth.tokens import TokenService
from backend.core.config import Settings, get_settings
from backend.core.lifespan import create_lifespan
from backend.core.logging import configure_logging


def _register_middlewares(app: FastAPI, settings: Settings, token_service: TokenService) -> None:
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CurrentUserMiddleware,
        token_service=token_service,
        access_cookie_name=settings.jwt.access_cookie_name,
    )


def _register_routers(app: FastAPI) -> None:
    for router in load_routers():
        app.include_router(router)


def create_app() -> FastAPI:
    settings: Settings = get_settings()
    configure_logging(settings)

    token_service = TokenService(settings)

    app = FastAPI(
        title=settings.project_name,
        description=settings.project_description,
        version=settings.project_version,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url=settings.openapi_url,
        default_response_class=ORJSONResponse,
        lifespan=create_lifespan(settings),
    )

    app.state.settings = settings
    app.state.token_service = token_service
    app.state.bot_runtime = None
    app.openapi_tags = [
        {"name": "health", "description": "Service health check operations"},
        {"name": "auth", "description": "Authentication and session management"},
        {
            "name": "users",
            "description": "User profile management, balance adjustments, session lifecycle, and GDPR stubs.",
        },
    ]

    _register_middlewares(app, settings, token_service)
    _register_routers(app)

    return app
