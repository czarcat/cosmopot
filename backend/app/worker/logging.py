from __future__ import annotations

from logging.config import dictConfig

import structlog
from structlog.contextvars import merge_contextvars


def configure_logging(level: str = "INFO") -> None:
    """Configure structured logging for the worker using structlog."""

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.processors.JSONRenderer(),
                }
            },
            "handlers": {
                "default": {
                    "level": level,
                    "class": "logging.StreamHandler",
                    "formatter": "structlog",
                }
            },
            "loggers": {
                "": {"handlers": ["default"], "level": level},
                "celery": {"handlers": ["default"], "level": level, "propagate": False},
            },
        }
    )

    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.StackInfoRenderer(omit_if_debug=True),
            structlog.processors.format_exc_info,
            structlog.processors.EventRenamer("message"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Helper returning a structured logger bound to *name*."""

    return structlog.get_logger(name)
