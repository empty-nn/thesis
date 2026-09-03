from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.full_model import KnowledgeGapORM
from db.session import get_db
from schemas.external_knowledge import ExternalKnowledgeDashboard
from services.knowledge_gaps import build_external_knowledge_dashboard
from services.session_auth import require_session_user_id


router = APIRouter(tags=["external-knowledge"])


@router.get(
    "/external-knowledge",
    response_model=ExternalKnowledgeDashboard,
)
def list_external_knowledge(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    ingestion_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ExternalKnowledgeDashboard:
    """Return the current user's external-recovery and knowledge-gap backlog."""
    user_id = require_session_user_id(request)
    statement = select(KnowledgeGapORM).where(
        KnowledgeGapORM.user_id == user_id
    )
    if ingestion_status:
        statement = statement.where(
            KnowledgeGapORM.ingestion_status == ingestion_status
        )
    gaps = db.scalars(
        statement.order_by(KnowledgeGapORM.created_at.desc()).limit(limit)
    ).all()
    return build_external_knowledge_dashboard(gaps)
