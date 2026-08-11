from fastapi import APIRouter, HTTPException

from schemas.chat import ChatRequest, ChatResponse
from services.answer_pipeline import run_chat_pipeline

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(request: ChatRequest) -> ChatResponse:
    """
    Main endpoint used by the Angular /chat screen.

    This is intentionally synchronous because the current retrieval stack
    contains blocking DB, model-inference, and DeepSeek SDK calls. FastAPI
    executes normal `def` path operations in its worker threadpool.
    """
    try:
        return run_chat_pipeline(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        # Keep the public error simple.
        # Log the original exception in production.
        raise HTTPException(
            status_code=500,
            detail=f"Travel pipeline failed: {exc}",
        ) from exc
