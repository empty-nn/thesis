from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from db.session import get_db
from services.session_auth import require_session_user_id
from services.conversation import save_chat_exchange

from schemas.chat import ChatRequest, ChatResponse
from services.answer_pipeline import run_chat_pipeline

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """
    Main endpoint used by the Angular /chat screen.

    This is intentionally synchronous because the current retrieval stack
    contains blocking DB, model-inference, and DeepSeek SDK calls. FastAPI
    executes normal `def` path operations in its worker threadpool.
    """
    request.user_id = require_session_user_id(http_request)

    try:
        result = run_chat_pipeline(request)
        if request.user_id:
            result.conversation_id = save_chat_exchange(
                db=db,
                user_id=request.user_id,
                user_message=request.message,
                assistant_message=result.answer,
                conversation_id=request.conversation_id,
            )
        return result
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
