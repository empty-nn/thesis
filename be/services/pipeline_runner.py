from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter

from langchain_core.documents import Document

from schemas.pipeline import (
    ParsedQuery,
    RetrievalConfidence,
    UserTravelMemory,
)
from services.memory import get_user_memory
from services.query_processing import (
    parse_query,
    rewrite_query,
)
from services.retrieval import (
    RetrievalFilters,
    bm25_search,
    build_retrieval_filters,
    fuse_results,
    rerank_documents,
    vector_search,
)


@dataclass
class PipelineTimings:
    rewrite_ms: float = 0.0
    parse_ms: float = 0.0
    memory_ms: float = 0.0
    filter_ms: float = 0.0
    vector_ms: float = 0.0
    bm25_ms: float = 0.0
    hybrid_ms: float = 0.0
    rerank_ms: float = 0.0
    final_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class RetrievalArtifacts:
    original_query: str
    rewritten_query: str

    parsed: ParsedQuery
    memory: UserTravelMemory
    filters: RetrievalFilters

    vector_docs: list[Document]
    bm25_docs: list[Document]
    fused_docs: list[Document]
    candidates: list[Document]
    reranked_docs: list[Document]

    confidence: RetrievalConfidence
    timings: PipelineTimings


def evaluate_retrieval_confidence(
    documents: list[Document],
) -> RetrievalConfidence:
    import numpy as np

    if not documents:
        return RetrievalConfidence(
            level="low",
            score=0.0,
            evidence_count=0,
        )

    rerank_scores = [
        doc.metadata.get(
            "rerank_score"
        )
        for doc in documents
    ]

    rerank_scores = [
        float(score)
        for score in rerank_scores
        if score is not None
    ]

    if not rerank_scores:
        return RetrievalConfidence(
            level="low",
            score=0.2,
            evidence_count=len(
                documents
            ),
        )

    top_score = rerank_scores[0]

    score_gap = (
        rerank_scores[0]
        - rerank_scores[1]
        if len(rerank_scores) > 1
        else 0.0
    )

    array = np.array(
        rerank_scores,
        dtype=float,
    )

    exp_scores = np.exp(
        array - np.max(array)
    )

    probabilities = (
        exp_scores
        / exp_scores.sum()
    )

    top_share = float(
        probabilities[0]
    )

    evidence_factor = min(
        len(documents) / 5,
        1.0,
    )

    confidence = (
        0.7 * top_share
        + 0.3 * evidence_factor
    )

    if confidence >= 0.7:
        level = "high"
    elif confidence >= 0.4:
        level = "medium"
    else:
        level = "low"

    return RetrievalConfidence(
        level=level,
        score=round(
            confidence,
            4,
        ),
        evidence_count=len(
            documents
        ),
        top_score=top_score,
        score_gap=score_gap,
    )


def _elapsed_ms(
    start: float,
) -> float:
    return round(
        (
            perf_counter()
            - start
        )
        * 1000,
        3,
    )


def run_retrieval_pipeline(
    query: str,
    conversation_history: list[dict] | None = None,
    user_id: str | None = None,
    vector_limit: int = 30,
    bm25_limit: int = 30,
    fusion_top_k: int = 20,
    rerank_top_k: int = 8,
    target_lat: float | None = None,
    target_lon: float | None = None,
) -> RetrievalArtifacts:
    query = query.strip()

    if not query:
        raise ValueError(
            "Query cannot be empty"
        )

    history = (
        conversation_history
        or []
    )

    timings = PipelineTimings()
    total_start = perf_counter()

    start = perf_counter()
    rewritten_query = rewrite_query(
        query=query,
        conversation_history=history,
    )
    timings.rewrite_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    parsed = parse_query(
        rewritten_query
    )
    timings.parse_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    memory = get_user_memory(
        user_id
    )
    timings.memory_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    filters = build_retrieval_filters(
        parsed
    )
    timings.filter_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    vector_docs = vector_search(
        query=rewritten_query,
        filters=filters,
        limit=vector_limit,
    )
    timings.vector_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    bm25_docs = bm25_search(
        query=rewritten_query,
        filters=filters,
        limit=bm25_limit,
    )
    timings.bm25_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    fused_docs = fuse_results(
        vector_docs=vector_docs,
        bm25_docs=bm25_docs,
        parsed=parsed,
        memory=memory,
        target_lat=target_lat,
        target_lon=target_lon,
    )
    candidates = fused_docs[
        :fusion_top_k
    ]
    timings.hybrid_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    reranked_docs = rerank_documents(
        query=rewritten_query,
        documents=candidates,
        top_k=rerank_top_k,
    )
    timings.rerank_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    confidence = (
        evaluate_retrieval_confidence(
            reranked_docs
        )
    )
    timings.final_ms = _elapsed_ms(
        start
    )

    timings.total_ms = _elapsed_ms(
        total_start
    )

    return RetrievalArtifacts(
        original_query=query,
        rewritten_query=(
            rewritten_query
        ),
        parsed=parsed,
        memory=memory,
        filters=filters,
        vector_docs=vector_docs,
        bm25_docs=bm25_docs,
        fused_docs=fused_docs,
        candidates=candidates,
        reranked_docs=reranked_docs,
        confidence=confidence,
        timings=timings,
    )


def filters_to_dict(
    filters: RetrievalFilters,
) -> dict:
    return asdict(filters)
