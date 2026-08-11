from fastapi import APIRouter, HTTPException

from schemas.retrieval_debug import (
    RetrievalDebugRequest,
    RetrievalDebugResponse,
)
from services.debug_pipeline import run_debug_pipeline

router = APIRouter(tags=["retrieval-debug"])


@router.post(
    "/retrieval/debug",
    response_model=RetrievalDebugResponse,
)
def retrieval_debug(
    request: RetrievalDebugRequest,
) -> RetrievalDebugResponse:
    """
    Run the same retrieval stages as the chatbot, but return every stage
    for the Angular Retrieval Debug screen.
    """
    try:
        return run_debug_pipeline(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval debug failed: {exc}",
        ) from exc
