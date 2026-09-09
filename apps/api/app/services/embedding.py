import re
import time
from typing import Protocol

from google import genai
from google.genai import errors, types

from app.core.config import settings

RETRY_STATUSES = {429, 500, 502, 503, 504}
_RETRY_SECONDS_RE = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)


class Embedder(Protocol):
    """Turns text into dense vector embeddings."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class GoogleEmbedder:
    """Embeds text using the Gemini ``gemini-embedding-001`` model.

    Free-tier embedding is limited (default 100 requests/minute), so the
    embedder throttles requests and retries transient 429/5xx errors with
    backoff to avoid exhausting the quota.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = settings.embedding_model,
        dimensions: int = settings.embedding_dimensions,
        batch_size: int = settings.embedding_batch_size,
        requests_per_minute: int = settings.embedding_requests_per_minute,
        max_retries: int = 5,
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._min_interval = 60.0 / max(requests_per_minute, 1)
        self._last_request_at = 0.0
        self._client = genai.Client(api_key=api_key) if api_key else None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client is None:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured; cannot generate embeddings"
            )

        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            response = self._embed_batch(batch)
            embeddings.extend(
                embedding.values for embedding in response.embeddings
            )
        return embeddings

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _embed_batch(self, batch: list[str]) -> object:
        self._throttle()
        for attempt in range(self._max_retries):
            try:
                return self._client.models.embed_content(
                    model=self._model,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self._dimensions
                    ),
                )
            except errors.APIError as error:
                if error.code not in RETRY_STATUSES:
                    raise
                delay = _extract_retry_seconds(str(error))
                if delay is None:
                    delay = min(2**attempt, 30)
                print(
                    f"embedding request throttled (HTTP {error.status}); "
                    f"retrying in {delay:.1f}s"
                )
                time.sleep(delay)
        raise RuntimeError(
            "embedding request failed after repeated retries"
        )


def _extract_retry_seconds(message: str) -> float | None:
    match = _RETRY_SECONDS_RE.search(message)
    return float(match.group(1)) if match else None