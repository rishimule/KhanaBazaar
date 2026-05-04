from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Khana Bazaar API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # JWT
    JWT_SECRET: str
    JWT_EXPIRES_HOURS: int = 24

    # OTP
    OTP_PEPPER: str
    OTP_TTL_SECONDS: int = 600
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN: int = 60
    OTP_MAX_PER_HOUR: int = 5

    # Email: "console" (dev/test) or "resend" (production)
    EMAIL_PROVIDER: str = "console"
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""

    DATABASE_URL: str
    REDIS_URL: str

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _force_asyncpg_driver(cls, v: str) -> str:
        # Render Postgres exposes a `postgres://` URL; SQLModel needs asyncpg.
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()
