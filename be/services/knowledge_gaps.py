from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from db.full_model import KnowledgeGapORM
from schemas.external_knowledge import (
    ExternalKnowledgeDashboard,
    ExternalKnowledgeRecord,
    ExternalKnowledgeSourceItem,
    ExternalKnowledgeSummary,
    ExternalRequirementItem,
)


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
        external_sources=payload.get("external_sources") or [],
        external_recovery=payload.get("external_recovery") or {},
        ingestion_status=payload.get("ingestion_status") or "pending_review",
        status="open",
    )
    db.add(gap)
    db.commit()
    db.refresh(gap)
    return gap


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _source_item(payload: dict[str, Any]) -> ExternalKnowledgeSourceItem:
    domain = str(payload.get("domain") or "unknown").strip()
    title = str(payload.get("title") or domain or "Untitled source").strip()
    return ExternalKnowledgeSourceItem(
        source_id=str(payload.get("id") or "").strip() or None,
        title=title,
        url=str(payload.get("url") or "").strip() or None,
        domain=domain,
        source_type=str(payload.get("source_type") or "open_web"),
        cited_in_answer=bool(payload.get("cited_in_answer")),
        consulted=bool(payload.get("consulted", True)),
        verification_status=str(
            payload.get("verification_status") or "unverified"
        ),
        freshness_metadata_status=str(
            payload.get("freshness_metadata_status") or "unknown"
        ),
        published_at=payload.get("published_at"),
        source_updated_at=payload.get("updated_at"),
        fetched_at=payload.get("fetched_at"),
    )


def _requirement_item(payload: dict[str, Any]) -> ExternalRequirementItem:
    return ExternalRequirementItem(
        requirement=str(payload.get("requirement") or "Unspecified requirement"),
        freshness_class=str(payload.get("freshness_class") or "stable"),
        search_eligible=bool(payload.get("search_eligible")),
        external_search_status=str(
            payload.get("external_search_status") or "not_attempted"
        ),
        review_status=str(payload.get("review_status") or "pending_review"),
        freshness_validation=str(
            payload.get("freshness_validation") or "not_required"
        ),
    )


def build_external_knowledge_dashboard(
    gaps: Iterable[KnowledgeGapORM],
) -> ExternalKnowledgeDashboard:
    records: list[ExternalKnowledgeRecord] = []
    unique_source_keys: set[str] = set()
    status_counts: dict[str, int] = {}
    pending_review = 0
    successful_recoveries = 0
    uncovered_requirements = 0

    for gap in gaps:
        recovery = (
            gap.external_recovery
            if isinstance(gap.external_recovery, dict)
            else {}
        )
        source_payloads = _object_list(gap.external_sources)
        sources = [_source_item(item) for item in source_payloads]
        requirements = [
            _requirement_item(item)
            for item in _object_list(recovery.get("requirements"))
        ]
        missing_requirements = _string_list(gap.missing_requirements)
        external_status = str(recovery.get("status") or "not_attempted")
        ingestion_status = str(gap.ingestion_status or "pending_review")

        status_counts[external_status] = status_counts.get(external_status, 0) + 1
        pending_review += int(ingestion_status == "pending_review")
        successful_recoveries += int(
            external_status == "completed" and bool(recovery.get("answer_generated"))
        )
        uncovered_requirements += len(missing_requirements)
        for source in sources:
            unique_source_keys.add(
                source.url or f"{source.domain}:{source.title}".casefold()
            )

        records.append(ExternalKnowledgeRecord(
            id=gap.id,
            query=gap.query,
            rewritten_query=gap.rewritten_query,
            missing_requirements=missing_requirements,
            recovery_queries=_string_list(gap.recovery_queries),
            external_status=external_status,
            external_model=(
                str(recovery.get("model")) if recovery.get("model") else None
            ),
            answer_generated=bool(recovery.get("answer_generated")),
            source_count=len(sources),
            cited_source_count=sum(item.cited_in_answer for item in sources),
            ingestion_status=ingestion_status,
            status=str(gap.status or "open"),
            sources=sources,
            requirements=requirements,
            created_at=gap.created_at,
            updated_at=gap.updated_at,
        ))

    return ExternalKnowledgeDashboard(
        summary=ExternalKnowledgeSummary(
            total_records=len(records),
            pending_review=pending_review,
            successful_recoveries=successful_recoveries,
            unique_sources=len(unique_source_keys),
            uncovered_requirements=uncovered_requirements,
        ),
        status_counts=status_counts,
        records=records,
    )
