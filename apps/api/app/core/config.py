from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    seed_admin_display_name: str = "Administrator"
    seed_admin_email_address: str = "admin@local.invalid"
    seed_admin_password: SecretStr = SecretStr("admin")
    seed_test_display_name: str = "Test User"
    seed_test_email_address: str = "test-user@local.invalid"
    seed_test_password: SecretStr = SecretStr("test")
    dev_auth_enabled: bool = False

    gemini_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-004"
    embedding_dimensions: int = 768
    embedding_batch_size: int = 100
    chat_model: str = "gemini-2.5-flash-lite"
    vector_top_k: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
