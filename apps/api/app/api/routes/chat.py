import json
import logging
from collections.abc import Iterator

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from google.genai import errors

from app.api.dependencies import ChatServiceDep, OptionalCurrentUser
from app.schemas.chat import ChatRequest


router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error_code(error: BaseException) -> str:
    """Classify a failed stream for client-side diagnostics only.

    The client renders a generic public message regardless; this stable code
    lets us distinguish a timeout from an ordinary upstream failure without
    exposing provider diagnostics.
    """

    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "chat_timeout"
    if isinstance(error, errors.APIError) and error.code in {408, 504}:
        return "chat_timeout"
    return "chat_unavailable"


@router.post("/stream")
def stream_chat(
    payload: ChatRequest,
    service: ChatServiceDep,
    _current_user: OptionalCurrentUser,
) -> StreamingResponse:
    """Stream answer deltas and finish with the sources used by the answer."""

    def events() -> Iterator[str]:
        try:
            for event, data in service.stream_answer(
                payload.question,
                history=payload.history,
                current_user=_current_user,
            ):
                if event == "sources":
                    sources = [source.model_dump(mode="json") for source in data]
                    yield _sse(event, sources)
                else:
                    yield _sse(event, data)
        except Exception as error:
            logger.exception(
                "Chat stream failed error=%s status=%s code=%s",
                type(error).__name__,
                getattr(error, "code", None),
                _error_code(error),
            )
            yield _sse("error", {"code": _error_code(error)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
