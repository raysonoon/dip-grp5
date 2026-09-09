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

    storage_backend: str = "local"
    # future migration to Cloudflare R2 object storage for images
    r2_account_id: str | None = None
    r2_bucket: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_public_base_url: str | None = None

    gemini_api_key: SecretStr | None = None
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768
    embedding_batch_size: int = 100
    embedding_requests_per_minute: int = 90
    chat_model: str = "gemini-3.5-flash-lite"
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
