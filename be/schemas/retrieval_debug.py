from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.chat import ConversationMessage

RetrievalStageName = Literal[
    "vector",
    "bm25",
    "hybrid",
    "rerank",
    "final",
]


class RetrievalDebugRequest(BaseModel):
    query: str = Field(min_length=1)

    conversation_history: list[ConversationMessage] = Field(
        default_factory=list
    )
    user_id: str | None = None

    vector_limit: int = Field(
        default=30,
        ge=1,
        le=100,
    )
    bm25_limit: int = Field(
        default=30,
        ge=1,
        le=100,
    )
    fusion_top_k: int = Field(
        default=20,
        ge=1,
        le=100,
    )
    rerank_top_k: int = Field(
        default=8,
        ge=1,
        le=50,
    )

    target_lat: float | None = Field(
        default=None,
        ge=-90,
        le=90,
    )
    target_lon: float | None = Field(
        default=None,
        ge=-180,
        le=180,
    )


class RetrievalChunkMetadata(BaseModel):
    country: str | None = None
    province: str | None = None
    city: str | None = None

    placeName: str | None = None
    placeType: str | None = None
    chunkTopic: str | None = None

    travelStyles: list[str] = Field(
        default_factory=list
    )
    activities: list[str] = Field(
        default_factory=list
    )
    suitableFor: list[str] = Field(
        default_factory=list
    )

    vectorRank: int | None = None
    bm25Rank: int | None = None

    vectorDistance: float | None = None
    metadataBoost: float | None = None
    geoBoost: float | None = None
    freshnessBoost: float | None = None
    geoDistanceKm: float | None = None


class RetrievalChunk(BaseModel):
    # Real rag_chunks IDs are UUIDs, so this must be a string.
    id: str
    rank: int
    score: float

    vectorScore: float | None = None
    bm25Score: float | None = None
    rerankScore: float | None = None

    title: str
    city: str | None = None
    placeName: str | None = None
    topic: str | None = None

    sourceName: str
    sourceUrl: str | None = None

    content: str
    metadata: RetrievalChunkMetadata


class RetrievalStageResult(BaseModel):
    stage: RetrievalStageName
    label: str
    durationMs: float
    chunks: list[RetrievalChunk]


class RetrievalDebugDiagnostics(BaseModel):
    originalQuery: str
    rewrittenQuery: str
    parsedQuery: dict[str, Any]
    userMemory: dict[str, Any]
    filters: dict[str, Any]
    retrievalPlan: dict[str, Any] | None = None
    evidenceCoverage: dict[str, Any] | None = None
    recoveryChunkCount: int = 0
    retrievalConfidence: dict[str, Any] | None = None

    rewriteDurationMs: float = 0
    parseDurationMs: float = 0
    memoryDurationMs: float = 0
    filterDurationMs: float = 0
    plannerDurationMs: float = 0
    checkerDurationMs: float = 0
    recoveryDurationMs: float = 0
    generationDurationMs: float = 0


class RetrievalDebugResponse(BaseModel):
    query: str
    createdAt: datetime
    totalDurationMs: float
    answer: str

    stages: dict[
        RetrievalStageName,
        RetrievalStageResult,
    ]

    diagnostics: RetrievalDebugDiagnostics
