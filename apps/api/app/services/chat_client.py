"""Bound Gemini calls made while a user is waiting for a chat answer."""

from google import genai
from google.genai import types

from app.core.config import settings


def create_chat_client() -> object | None:
    if settings.gemini_api_key is None:
        return None
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=settings.chat_request_timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
