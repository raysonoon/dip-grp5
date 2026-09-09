from fastapi import APIRouter

from app.api.dependencies import ChatServiceDep
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def ask_chat(
    payload: ChatRequest,
    service: ChatServiceDep,
) -> ChatResponse:
    """Answer a question using vector retrieval over the knowledge base."""
    return service.answer(payload.question)