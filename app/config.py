from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    gemini_api_key: str
    supabase_url: str
    supabase_key: str
    sentry_dsn: str
    redis_url: str = "redis://redis:6379"
    dev_mode: bool = False

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
