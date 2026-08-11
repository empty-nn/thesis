from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.documents import Document

from schemas.retrieval_debug import (
    RetrievalChunk,
    RetrievalChunkMetadata,
    RetrievalDebugDiagnostics,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
    RetrievalStageResult,
    RetrievalStageName,
)
from services.pipeline_runner import (
    filters_to_dict,
    run_retrieval_pipeline,
)
from services.retrieval import (
    source_name,
)


def _safe_float(value) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stage_score(
    doc: Document,
    stage: RetrievalStageName,
) -> float:
    metadata = doc.metadata

    if stage == "vector":
        return float(
            metadata.get(
                "vector_score"
            )
            or 0.0
        )

    if stage == "bm25":
        return float(
            metadata.get(
                "bm25_score"
            )
            or 0.0
        )

    if stage == "hybrid":
        return float(
            metadata.get(
                "fusion_score"
            )
            or 0.0
        )

    return float(
        metadata.get(
            "rerank_score"
        )
        or 0.0
    )


def _chunk_title(
    doc: Document,
) -> str:
    metadata = doc.metadata

    return (
        metadata.get(
            "place_name"
        )
        or metadata.get(
            "section_heading"
        )
        or metadata.get(
            "chunk_topic"
        )
        or f"Chunk {metadata.get('chunk_id')}"
    )


def _to_debug_chunk(
    doc: Document,
    rank: int,
    stage: RetrievalStageName,
) -> RetrievalChunk:
    metadata = doc.metadata

    source_url = metadata.get(
        "source_location"
    )

    return RetrievalChunk(
        id=str(
            metadata.get(
                "chunk_id"
            )
        ),
        rank=rank,
        score=_stage_score(
            doc,
            stage,
        ),

        vectorScore=_safe_float(
            metadata.get(
                "vector_score"
            )
        ),
        bm25Score=_safe_float(
            metadata.get(
                "bm25_score"
            )
        ),
        rerankScore=_safe_float(
            metadata.get(
                "rerank_score"
            )
        ),

        title=_chunk_title(
            doc
        ),
        city=metadata.get(
            "city"
        ),
        placeName=metadata.get(
            "place_name"
        ),
        topic=metadata.get(
            "chunk_topic"
        ),

        sourceName=source_name(
            source_url
        ),
        sourceUrl=source_url,

        content=doc.page_content,

        metadata=RetrievalChunkMetadata(
            country=metadata.get(
                "country"
            ),
            province=metadata.get(
                "province"
            ),
            city=metadata.get(
                "city"
            ),

            placeName=metadata.get(
                "place_name"
            ),
            placeType=metadata.get(
                "place_type"
            ),
            chunkTopic=metadata.get(
                "chunk_topic"
            ),

            travelStyles=metadata.get(
                "ai_travel_styles"
            ) or [],
            activities=metadata.get(
                "ai_activities"
            ) or [],
            suitableFor=metadata.get(
                "ai_suitable_for"
            ) or [],

            vectorRank=metadata.get(
                "vector_rank"
            ),
            bm25Rank=metadata.get(
                "bm25_rank"
            ),

            vectorDistance=_safe_float(
                metadata.get(
                    "vector_distance"
                )
            ),
            metadataBoost=_safe_float(
                metadata.get(
                    "metadata_boost"
                )
            ),
            geoBoost=_safe_float(
                metadata.get(
                    "geo_boost"
                )
            ),
            freshnessBoost=_safe_float(
                metadata.get(
                    "freshness_boost"
                )
            ),
            geoDistanceKm=_safe_float(
                metadata.get(
                    "geo_distance_km"
                )
            ),
        ),
    )


def _stage(
    name: RetrievalStageName,
    label: str,
    duration_ms: float,
    documents: list[Document],
) -> RetrievalStageResult:
    return RetrievalStageResult(
        stage=name,
        label=label,
        durationMs=duration_ms,
        chunks=[
            _to_debug_chunk(
                doc=doc,
                rank=rank,
                stage=name,
            )
            for rank, doc in enumerate(
                documents,
                start=1,
            )
        ],
    )


def run_debug_pipeline(
    request: RetrievalDebugRequest,
) -> RetrievalDebugResponse:
    history = [
        item.model_dump()
        for item
        in request.conversation_history
    ]

    artifacts = (
        run_retrieval_pipeline(
            query=request.query,
            conversation_history=history,
            user_id=request.user_id,
            vector_limit=(
                request.vector_limit
            ),
            bm25_limit=(
                request.bm25_limit
            ),
            fusion_top_k=(
                request.fusion_top_k
            ),
            rerank_top_k=(
                request.rerank_top_k
            ),
            target_lat=(
                request.target_lat
            ),
            target_lon=(
                request.target_lon
            ),
        )
    )

    # "final" is the evidence set used by the current notebook.
    # There is no additional pruning after reranking in the notebook.
    final_docs = (
        artifacts.reranked_docs
    )

    stages = {
        "vector": _stage(
            "vector",
            "Vector",
            artifacts.timings.vector_ms,
            artifacts.vector_docs,
        ),
        "bm25": _stage(
            "bm25",
            "BM25",
            artifacts.timings.bm25_ms,
            artifacts.bm25_docs,
        ),
        "hybrid": _stage(
            "hybrid",
            "Hybrid",
            artifacts.timings.hybrid_ms,
            artifacts.candidates,
        ),
        "rerank": _stage(
            "rerank",
            "Rerank",
            artifacts.timings.rerank_ms,
            artifacts.reranked_docs,
        ),
        "final": _stage(
            "final",
            "Final",
            artifacts.timings.final_ms,
            final_docs,
        ),
    }

    return RetrievalDebugResponse(
        query=request.query,
        createdAt=datetime.now(
            timezone.utc
        ),
        totalDurationMs=(
            artifacts.timings.total_ms
        ),
        stages=stages,
        diagnostics=(
            RetrievalDebugDiagnostics(
                originalQuery=(
                    artifacts.original_query
                ),
                rewrittenQuery=(
                    artifacts.rewritten_query
                ),
                parsedQuery=(
                    artifacts.parsed.model_dump()
                ),
                filters=filters_to_dict(
                    artifacts.filters
                ),
                retrievalConfidence=(
                    artifacts.confidence.model_dump()
                ),

                rewriteDurationMs=(
                    artifacts.timings.rewrite_ms
                ),
                parseDurationMs=(
                    artifacts.timings.parse_ms
                ),
                memoryDurationMs=(
                    artifacts.timings.memory_ms
                ),
                filterDurationMs=(
                    artifacts.timings.filter_ms
                ),
            )
        ),
    )
