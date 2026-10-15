import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.dependencies import ChatServiceDep, OptionalCurrentUser
from app.schemas.chat import ChatRequest


router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def stream_chat(
    payload: ChatRequest,
    service: ChatServiceDep,
    _current_user: OptionalCurrentUser,
) -> StreamingResponse:
    """Stream answer deltas and finish with the sources used by the answer."""

    def events() -> Iterator[str]:
        try:
            picker_context = {"food_pick": payload.food_pick} if payload.food_pick else {}
            logger.info("Chat picker result: %r", payload.food_pick)
            if payload.action == "recommend_pick":
                picker_context["recommend_pick"] = True
            for event, data in service.stream_answer(
                payload.question or "",
                history=payload.history,
                **picker_context,
            ):
                if event == "sources":
                    sources = [source.model_dump(mode="json") for source in data]
                    yield _sse(event, sources)
                else:
                    yield _sse(event, data)
        except Exception:
            logger.exception("Chat stream failed")
            yield _sse("error", {"code": "chat_unavailable"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
