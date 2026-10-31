"""Bound Gemini calls made while a user is waiting for a chat answer."""

from google import genai
from google.genai import types

from app.core.config import settings


def create_chat_client() -> object | None:
    """Build the shared interactive client."""
    if settings.gemini_api_key is None:
        return None
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=settings.chat_request_timeout_ms,
            retry_options=types.HttpRetryOptions(
                attempts=settings.chat_retry_attempts,
                initial_delay=settings.chat_retry_initial_delay_ms / 1000,
                max_delay=settings.chat_retry_max_delay_ms / 1000,
            ),
        ),
    )
