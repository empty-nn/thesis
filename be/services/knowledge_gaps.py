from __future__ import annotations

from sqlalchemy.orm import Session

from db.full_model import KnowledgeGapORM


def save_knowledge_gap(
    db: Session,
    *,
    user_id: str | None,
    conversation_id: str | None,
    payload: dict,
) -> KnowledgeGapORM:
    gap = KnowledgeGapORM(
        user_id=user_id,
        conversation_id=conversation_id,
        query=payload["query"],
        rewritten_query=payload.get("rewritten_query"),
        missing_requirements=payload.get("missing_requirements") or [],
        recovery_queries=payload.get("recovery_queries") or [],
        top_evidence=payload.get("top_evidence") or [],
        status="open",
    )
    db.add(gap)
    db.commit()
    db.refresh(gap)
    return gap
