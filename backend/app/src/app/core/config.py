from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Khana Bazaar API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    ENVIRONMENT: str = "development"

    FIREBASE_PROJECT_ID: str
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    DATABASE_URL: str
    REDIS_URL: str

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

settings = Settings()
