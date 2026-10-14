import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.dependencies import ChatServiceDep, OptionalCurrentUser
from app.schemas.chat import ChatRequest


router = APIRouter(prefix="/chat", tags=["chat"])


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
        for event, data in service.stream_answer(
            payload.question,
            history=payload.history,
        ):
            if event == "sources":
                sources = [source.model_dump(mode="json") for source in data]
                yield _sse(event, sources)
            else:
                yield _sse(event, data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
