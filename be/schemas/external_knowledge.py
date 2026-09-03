from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas.camel_model import CamelModel


class ExternalKnowledgeSourceItem(CamelModel):
    source_id: str | None = None
    title: str
    url: str | None = None
    domain: str
    source_type: str
    cited_in_answer: bool = False
    consulted: bool = True
    verification_status: str = "unverified"
    freshness_metadata_status: str = "unknown"
    published_at: str | None = None
    source_updated_at: str | None = None
    fetched_at: str | None = None


class ExternalRequirementItem(CamelModel):
    requirement: str
    freshness_class: str = "stable"
    search_eligible: bool = False
    external_search_status: str = "not_attempted"
    review_status: str = "pending_review"
    freshness_validation: str = "not_required"


class ExternalKnowledgeRecord(CamelModel):
    id: int
    query: str
    rewritten_query: str | None = None
    missing_requirements: list[str] = Field(default_factory=list)
    recovery_queries: list[str] = Field(default_factory=list)
    external_status: str
    external_model: str | None = None
    answer_generated: bool = False
    source_count: int = 0
    cited_source_count: int = 0
    ingestion_status: str
    status: str
    sources: list[ExternalKnowledgeSourceItem] = Field(default_factory=list)
    requirements: list[ExternalRequirementItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ExternalKnowledgeSummary(CamelModel):
    total_records: int
    pending_review: int
    successful_recoveries: int
    unique_sources: int
    uncovered_requirements: int


class ExternalKnowledgeDashboard(CamelModel):
    summary: ExternalKnowledgeSummary
    status_counts: dict[str, int] = Field(default_factory=dict)
    records: list[ExternalKnowledgeRecord] = Field(default_factory=list)
