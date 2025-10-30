from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import (
    AliasChoices,
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.core.constants import DEFAULT_ENV_FILE, SECRETS_DIR, SERVICE_NAME


class Environment(StrEnum):
    """Deployment environments supported by the service."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AsyncPostgresDsn(AnyUrl):
    allowed_schemes = {"postgresql", "postgresql+asyncpg"}
    host_required = True


class DatabaseSettings(BaseModel):
    """Database connectivity configuration."""

    model_config = ConfigDict(extra="ignore")

    url: AsyncPostgresDsn | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE__URL", "database__url", "DATABASE_URL", "database_url"),
    )
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: SecretStr = SecretStr("postgres")
    name: str = SERVICE_NAME
    echo: bool = False

    @computed_field(return_type=str)
    def dsn(self) -> str:
        """Assemble the SQLAlchemy async DSN."""

        if self.url is not None:
            return str(self.url)

        password = quote_plus(self.password.get_secret_value())
        return (
            f"postgresql+asyncpg://{self.user}:{password}@{self.host}:{self.port}/{self.name}"
        )

    @computed_field(return_type=str)
    def async_fallback_dsn(self) -> str:
        """Alias retained for external tooling expecting `async_fallback_dsn`."""

        return self.dsn


class Settings(BaseSettings):
    """Application settings loaded from the environment or secret stores."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_nested_delimiter="__",
        secrets_dir=SECRETS_DIR,
        extra="ignore",
        validate_default=True,
        case_sensitive=False,
    )

    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: str = "INFO"

    project_name: str = "Backend Service"
    project_description: str = "Backend FastAPI service"
    project_version: str = "0.1.0"
    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str = "/openapi.json"

    cors_allow_origins: list[str] = Field(default_factory=list)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    @model_validator(mode="after")
    def _normalize(self) -> "Settings":
        self.log_level = self.log_level.upper()

        if self.environment in {Environment.DEVELOPMENT, Environment.TEST}:
            self.debug = True

        return self

    @computed_field(return_type=bool)
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT

    @computed_field(return_type=bool)
    def is_testing(self) -> bool:
        return self.environment is Environment.TEST

    @computed_field(return_type=bool)
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""

    return Settings()
