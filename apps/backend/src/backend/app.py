from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from backend.api.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from backend.api.routes import load_routers
from backend.core.config import Settings, get_settings
from backend.core.lifespan import create_lifespan
from backend.core.logging import configure_logging


def _register_middlewares(app: FastAPI, settings: Settings) -> None:
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


def _register_routers(app: FastAPI) -> None:
    for router in load_routers():
        app.include_router(router)


def create_app() -> FastAPI:
    settings: Settings = get_settings()
    configure_logging(settings)

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
    app.openapi_tags = [
        {"name": "health", "description": "Service health check operations"},
        {
            "name": "users",
            "description": "User profile management, balance adjustments, session lifecycle, and GDPR stubs.",
        },
    ]

    _register_middlewares(app, settings)
    _register_routers(app)

    return app
