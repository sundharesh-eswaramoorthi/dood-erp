from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # app
    APP_NAME: str = "CHOLAVIN-ERP"
    ENV: str = "dev"
    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_TTL_MIN: int = 30
    REFRESH_TOKEN_TTL_DAYS: int = 14

    # postgres — owner/superuser role, used ONLY for migrations & role bootstrap
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "cholavin"
    POSTGRES_USER: str = "cholavin"
    POSTGRES_PASSWORD: str = "cholavin"

    # runtime application role — NOSUPERUSER so Row-Level Security actually applies.
    # (A superuser bypasses RLS; the app must not connect as one.)
    APP_DB_USER: str = "cholavin_app"
    APP_DB_PASSWORD: str = "cholavin_app"

    # infra
    REDIS_URL: str = "redis://redis:6379/0"
    MONGO_URL: str = "mongodb://mongo:27017"
    MONGO_DB: str = "cholavin"

    # seed
    SEED_ADMIN_USERNAME: str = "admin"
    SEED_ADMIN_PASSWORD: str = "admin123"

    @property
    def async_database_url(self) -> str:
        # FastAPI runtime — the RLS-subject app role.
        return (
            f"postgresql+asyncpg://{self.APP_DB_USER}:{self.APP_DB_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        # Celery worker + seed — also the RLS-subject app role.
        return (
            f"postgresql+psycopg2://{self.APP_DB_USER}:{self.APP_DB_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def migration_database_url(self) -> str:
        # Alembic — the owner/superuser role (creates tables, roles, grants).
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
