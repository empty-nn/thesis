import json
from queue import Queue
from threading import Thread

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from db.session import SessionLocal, get_db
from services.session_auth import require_session_user_id
from services.conversation import (
    get_user_conversation,
    list_user_conversations,
    save_chat_exchange,
)

from schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
)
from services.answer_pipeline import run_chat_pipeline
from services.memory import analyze_and_save_user_memory
from services.conversation_memory import update_conversation_memory
from services.knowledge_gaps import save_knowledge_gap
from services.llm_telemetry import telemetry_session
from services.pipeline_telemetry import save_pipeline_telemetry

router = APIRouter(tags=["chat"])


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    http_request: Request,
) -> StreamingResponse:
    """Stream real, safe stage summaries followed by the final chat result."""
    request.user_id = require_session_user_id(http_request)

    def event_stream():
        events: Queue[dict | None] = Queue()

        def emit(stage: str, payload: dict) -> None:
            events.put({
                "type": "stage",
                "stage": stage,
                **payload,
            })

        def run() -> None:
            db = SessionLocal()
            result: ChatResponse | None = None
            with telemetry_session() as telemetry:
                try:
                    result = run_chat_pipeline(
                        request,
                        progress_callback=emit,
                    )
                    if request.user_id:
                        result.conversation_id = save_chat_exchange(
                            db,
                            user_id=request.user_id,
                            user_message=request.message,
                            assistant_message=result.answer,
                            conversation_id=request.conversation_id,
                        )
                    if result.knowledge_gap:
                        try:
                            save_knowledge_gap(
                                db,
                                user_id=request.user_id,
                                conversation_id=result.conversation_id,
                                payload=result.knowledge_gap,
                            )
                        except Exception as exc:
                            db.rollback()
                            print(f"[KNOWLEDGE GAP WARNING] {exc}")

                    events.put({
                        "type": "complete",
                        "answer": result.answer,
                        "sources": [source.model_dump() for source in result.sources],
                        "conversation_id": result.conversation_id,
                    })
                except Exception as exc:
                    telemetry.mark_failed(exc)
                    events.put({
                        "type": "error",
                        "message": f"Travel pipeline failed: {exc}",
                    })
                finally:
                    save_pipeline_telemetry(
                        telemetry.snapshot(),
                        user_id=request.user_id,
                        conversation_id=(result.conversation_id if result else None),
                    )
                    db.close()
                    events.put(None)

            if (
                request.user_id
                and result
                and result.conversation_id
                and result.route_category == "travel"
            ):
                try:
                    analyze_and_save_user_memory(
                        request.user_id,
                        request.message,
                    )
                    update_conversation_memory(
                        request.user_id,
                        result.conversation_id,
                        request.message,
                        result.answer,
                    )
                except Exception as exc:
                    print(f"[CHAT MEMORY WARNING] {exc}")

        Thread(target=run, daemon=True).start()

        while True:
            event = events.get()
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def conversations(
    http_request: Request,
    db: Session = Depends(get_db),
) -> list[ConversationSummary]:
    user_id = require_session_user_id(http_request)
    return list_user_conversations(db, user_id)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
)
def conversation_detail(
    conversation_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    user_id = require_session_user_id(http_request)
    result = get_user_conversation(db, user_id, conversation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """
    Main endpoint used by the Angular /chat screen.

    This is intentionally synchronous because the current retrieval stack
    contains blocking DB, model-inference, and DeepSeek SDK calls. FastAPI
    executes normal `def` path operations in its worker threadpool.
    """
    request.user_id = require_session_user_id(http_request)

    with telemetry_session() as telemetry:
        result: ChatResponse | None = None
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
                if result.knowledge_gap:
                    try:
                        save_knowledge_gap(
                            db,
                            user_id=request.user_id,
                            conversation_id=result.conversation_id,
                            payload=result.knowledge_gap,
                        )
                    except Exception as exc:
                        db.rollback()
                        print(f"[KNOWLEDGE GAP WARNING] {exc}")
                if result.route_category == "travel":
                    background_tasks.add_task(
                        analyze_and_save_user_memory,
                        request.user_id,
                        request.message,
                    )
                    background_tasks.add_task(
                        update_conversation_memory,
                        request.user_id,
                        result.conversation_id,
                        request.message,
                        result.answer,
                    )
            return result
        except ValueError as exc:
            telemetry.mark_failed(exc)
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            telemetry.mark_failed(exc)
            raise HTTPException(
                status_code=500,
                detail=f"Travel pipeline failed: {exc}",
            ) from exc
        finally:
            save_pipeline_telemetry(
                telemetry.snapshot(),
                user_id=request.user_id,
                conversation_id=(result.conversation_id if result else None),
            )
