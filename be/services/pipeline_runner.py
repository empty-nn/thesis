from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import re
from time import perf_counter
from typing import Any, Callable

from langchain_core.documents import Document

from schemas.pipeline import (
    AgenticRetrievalPlan,
    AnswerReadiness,
    EvidenceCoverage,
    ParsedQuery,
    RetrievalConfidence,
    UserTravelMemory,
)
from services.agentic_retrieval import (
    check_evidence_coverage,
    merge_unique_documents,
    plan_retrieval,
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
    planner_ms: float = 0.0
    vector_ms: float = 0.0
    bm25_ms: float = 0.0
    hybrid_ms: float = 0.0
    rerank_ms: float = 0.0
    checker_ms: float = 0.0
    recovery_ms: float = 0.0
    final_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class RetrievalArtifacts:
    original_query: str
    rewritten_query: str

    parsed: ParsedQuery
    memory: UserTravelMemory
    filters: RetrievalFilters
    plan: AgenticRetrievalPlan

    vector_docs: list[Document]
    bm25_docs: list[Document]
    fused_docs: list[Document]
    candidates: list[Document]
    reranked_docs: list[Document]
    recovery_docs: list[Document]
    recovery_queries: list[str]

    confidence: RetrievalConfidence
    comparison_balance: dict[str, Any]
    recovery_effectiveness: dict[str, Any]
    answer_readiness: AnswerReadiness
    initial_coverage: EvidenceCoverage
    coverage: EvidenceCoverage
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


def _document_city(document: Document) -> str:
    return str(document.metadata.get("city") or "").strip().casefold()


def _document_identifier(document: Document) -> str:
    return str(document.metadata.get("chunk_id") or id(document))


def _select_balanced_by_city(
    documents: list[Document],
    cities: list[str],
    top_k: int,
    minimum_per_city: int,
) -> list[Document]:
    selected: list[Document] = []
    selected_ids: set[str] = set()
    for city in cities:
        city_key = city.strip().casefold()
        city_documents = [
            document for document in documents
            if _document_city(document) == city_key
        ]
        for document in city_documents[:minimum_per_city]:
            identifier = _document_identifier(document)
            if identifier not in selected_ids:
                selected.append(document)
                selected_ids.add(identifier)
    for document in documents:
        if len(selected) >= top_k:
            break
        identifier = _document_identifier(document)
        if identifier not in selected_ids:
            selected.append(document)
            selected_ids.add(identifier)
    # Quotas decide membership, while the original relevance order decides rank.
    return [
        document for document in documents
        if _document_identifier(document) in selected_ids
    ][:top_k]


def _rerank_with_comparison_balance(
    query: str,
    fused_documents: list[Document],
    comparison_cities: list[str],
    fusion_top_k: int,
    rerank_top_k: int,
) -> tuple[list[Document], list[Document], dict[str, Any]]:
    if not comparison_cities:
        candidates = fused_documents[:fusion_top_k]
        reranked = rerank_documents(
            query=query,
            documents=candidates,
            top_k=rerank_top_k,
        )
        return candidates, reranked, {"enabled": False}

    candidate_minimum = min(5, max(1, fusion_top_k // len(comparison_cities)))
    candidates = _select_balanced_by_city(
        fused_documents,
        comparison_cities,
        fusion_top_k,
        candidate_minimum,
    )
    ranked_candidates = rerank_documents(
        query=query,
        documents=candidates,
        top_k=len(candidates),
    )
    evidence_minimum = min(3, max(1, rerank_top_k // len(comparison_cities)))
    reranked = _select_balanced_by_city(
        ranked_candidates,
        comparison_cities,
        rerank_top_k,
        evidence_minimum,
    )
    selected_counts = {
        city: sum(
            _document_city(document) == city.strip().casefold()
            for document in reranked
        )
        for city in comparison_cities
    }
    underrepresented = [
        city for city, count in selected_counts.items()
        if count < evidence_minimum
    ]
    return candidates, reranked, {
        "enabled": True,
        "entities": comparison_cities,
        "target_minimum_per_entity": evidence_minimum,
        "selected_counts": selected_counts,
        "balanced": not underrepresented,
        "underrepresented_entities": underrepresented,
    }


def evaluate_answer_readiness(
    parsed: ParsedQuery,
    coverage: EvidenceCoverage,
    documents: list[Document],
) -> AnswerReadiness:
    distinct_places = {
        str(document.metadata.get("place_name")).strip()
        for document in documents
        if document.metadata.get("place_name")
    }
    duration_days = parsed.constraints.duration_days
    minimum_places = (
        min(duration_days, 3)
        if parsed.intent == "itinerary" and duration_days
        else (1 if parsed.intent == "itinerary" else 0)
    )
    enough_places = len(distinct_places) >= minimum_places
    if coverage.sufficient and enough_places:
        mode = "complete"
        reason = "All requirements have cited coverage and itinerary evidence is adequate."
    elif coverage.covered_count > 0 or (
        not coverage.requirement_assessments and bool(documents)
    ):
        mode = "partial"
        reason = (
            "Some requirements are supported, but the evidence is not adequate "
            "for a complete response."
        )
        if parsed.intent == "itinerary" and not enough_places:
            reason = (
                f"Only {len(distinct_places)} distinct supported place(s) are available; "
                f"at least {minimum_places} are required for this itinerary."
            )
    else:
        mode = "insufficient"
        reason = "No requested requirement has sufficient cited evidence."
    return AnswerReadiness(
        mode=mode,
        coverage_ratio=coverage.coverage_ratio,
        duration_days=duration_days,
        distinct_supported_place_count=len(distinct_places),
        minimum_required_place_count=minimum_places,
        reason=reason,
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
    use_agentic_retrieval: bool = True,
    memory_override: UserTravelMemory | None = None,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
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
    memory = (
        memory_override
        if memory_override is not None
        else get_user_memory(user_id)
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
    if progress_callback:
        parsed_constraints = {
            key: value
            for key, value in parsed.constraints.model_dump().items()
            if value is not None
        }
        explicit_constraints = [
            item.model_dump() for item in parsed.explicit_constraints
        ]
        retrieval_facets = {
            "location": parsed.location.model_dump(),
            "place_types": parsed.place_types,
            "activities": parsed.activities,
            "travel_styles": parsed.travel_styles,
            "suitable_for": parsed.suitable_for,
            "constraints": parsed.constraints.model_dump(),
        }
        understanding_highlights = [
            f"Standalone query: {rewritten_query}",
            f"Intent: {parsed.intent or 'travel information'}",
            f"Operation: {parsed.operation or 'lookup'}",
        ]
        if parsed.location.city:
            understanding_highlights.append(
                f"Destination: {parsed.location.city}"
            )
        if parsed_constraints:
            understanding_highlights.append(
                "Constraints: " + ", ".join(
                    f"{key.replace('_', ' ')}={value}"
                    for key, value in parsed_constraints.items()
                )
            )
        understanding_highlights.append(
            f"Context used: {len(history)} recent messages"
        )
        progress_callback("understanding", {
            "summary": (
                f"Understood a {parsed.intent or 'travel'} request"
                + (
                    f" for {parsed.location.city}"
                    if parsed.location.city else ""
                )
                + "."
            ),
            "rewritten_query": rewritten_query,
            "intent": parsed.intent,
            "operation": parsed.operation,
            "explicit_constraints": explicit_constraints,
            "retrieval_facets": retrieval_facets,
            "city": parsed.location.city,
            "history_messages_used": len(history),
            "constraints": parsed_constraints,
            "highlights": understanding_highlights,
        })

    start = perf_counter()
    comparison_cities = (
        list(parsed.location.cities)
        if (
            parsed.operation == "compare"
            and parsed.intent != "transport"
            and len(parsed.location.cities) >= 2
        )
        else []
    )
    plan = (
        plan_retrieval(
            rewritten_query,
            comparison_cities=comparison_cities,
        )
        if use_agentic_retrieval
        else AgenticRetrievalPlan(
            complexity="simple",
            requirements=[rewritten_query],
            retrieval_tasks=[{
                "task_type": "general",
                "query": rewritten_query,
                "top_k": min(vector_limit, bm25_limit),
                "cities": comparison_cities,
            }],
        )
    )
    timings.planner_ms = _elapsed_ms(start)
    if progress_callback:
        progress_callback("planning", {
            "summary": (
                f"Created {len(plan.retrieval_tasks)} focused search"
                f"{'es' if len(plan.retrieval_tasks) != 1 else ''} "
                f"for a {plan.complexity.replace('_', ' ')} request."
            ),
            "complexity": plan.complexity,
            "requirements": plan.requirements,
            "queries": [task.query for task in plan.retrieval_tasks],
            "query_scopes": [
                {
                    "query": task.query,
                    "cities": task.cities,
                    "requirement_indexes": task.requirement_indexes,
                    "top_k": task.top_k,
                }
                for task in plan.retrieval_tasks
            ],
            "highlights": [
                f"Complexity: {plan.complexity.replace('_', ' ')}",
                *(
                    ["Requirements: " + "; ".join(plan.requirements)]
                    if plan.requirements else []
                ),
                *[
                    f"Search {index}: {task.query} (top {task.top_k})"
                    + (f" [cities: {', '.join(task.cities)}]" if task.cities else "")
                    for index, task in enumerate(
                        plan.retrieval_tasks, start=1
                    )
                ],
            ],
        })

    vector_groups: list[list[Document]] = []
    bm25_groups: list[list[Document]] = []
    for task in plan.retrieval_tasks:
        task_filters = (
            replace(
                filters,
                city=task.cities[0] if len(task.cities) == 1 else None,
                cities=list(task.cities),
            )
            if task.cities else filters
        )
        start = perf_counter()
        vector_groups.append(
            vector_search(
                query=task.query,
                filters=task_filters,
                limit=min(vector_limit, task.top_k),
            )
        )
        timings.vector_ms += _elapsed_ms(start)

        start = perf_counter()
        bm25_groups.append(
            bm25_search(
                query=task.query,
                filters=task_filters,
                limit=min(bm25_limit, task.top_k),
            )
        )
        timings.bm25_ms += _elapsed_ms(start)

    vector_docs = merge_unique_documents(vector_groups)
    bm25_docs = merge_unique_documents(bm25_groups)

    start = perf_counter()
    fused_docs = fuse_results(
        vector_docs=vector_docs,
        bm25_docs=bm25_docs,
        parsed=parsed,
        memory=memory,
        target_lat=target_lat,
        target_lon=target_lon,
    )
    timings.hybrid_ms = _elapsed_ms(
        start
    )

    start = perf_counter()
    candidates, reranked_docs, comparison_balance = _rerank_with_comparison_balance(
        query=rewritten_query,
        fused_documents=fused_docs,
        comparison_cities=comparison_cities,
        fusion_top_k=fusion_top_k,
        rerank_top_k=rerank_top_k,
    )
    timings.rerank_ms = _elapsed_ms(
        start
    )
    if progress_callback:
        top_places = list(dict.fromkeys(
            doc.metadata.get("place_name")
            for doc in reranked_docs
            if doc.metadata.get("place_name")
        ))[:5]
        progress_callback("retrieval", {
            "summary": (
                f"Selected {len(reranked_docs)} relevant evidence items "
                f"from {len(candidates)} combined candidates."
            ),
            "search_count": len(plan.retrieval_tasks),
            "candidate_count": len(candidates),
            "evidence_count": len(reranked_docs),
            "comparison_balance": comparison_balance,
            "top_places": top_places,
            "highlights": [
                f"Ran {len(plan.retrieval_tasks)} planned search"
                f"{'es' if len(plan.retrieval_tasks) != 1 else ''}",
                f"Combined candidates: {len(candidates)}",
                f"Evidence selected after reranking: {len(reranked_docs)}",
                *(
                    ["Top places: " + ", ".join(top_places)]
                    if top_places else []
                ),
            ],
        })

    start = perf_counter()
    coverage = (
        check_evidence_coverage(
            query=rewritten_query,
            requirements=plan.requirements,
            documents=reranked_docs,
            telemetry_stage="coverage_checker_initial",
        )
        if use_agentic_retrieval
        else EvidenceCoverage(
            sufficient=bool(reranked_docs),
            covered_requirements=(
                plan.requirements if reranked_docs else []
            ),
        )
    )
    timings.checker_ms = _elapsed_ms(start)
    initial_coverage = coverage.model_copy(deep=True)
    initial_selected_ids = {
        _document_identifier(document) for document in reranked_docs
    }
    initial_candidate_ids = {
        _document_identifier(document)
        for document in [*vector_docs, *bm25_docs]
    }
    recovery_effectiveness: dict[str, Any] = {
        "performed": False,
        "coverage_ratio_before": initial_coverage.coverage_ratio,
        "coverage_ratio_after": initial_coverage.coverage_ratio,
        "new_unique_candidate_count": 0,
        "new_selected_evidence_ids": [],
        "newly_covered_requirements": [],
        "improved": False,
        "stop_reason": (
            "coverage_sufficient"
            if initial_coverage.sufficient
            else "no_recovery_queries"
        ),
    }
    if progress_callback:
        progress_callback("checking", {
            "summary": (
                "The evidence covers all requested topics."
                if coverage.sufficient
                else "Some requested topics need additional evidence."
            ),
            "sufficient": coverage.sufficient,
            "coverage_ratio": coverage.coverage_ratio,
            "requirement_assessments": [
                item.model_dump() for item in coverage.requirement_assessments
            ],
            "covered": coverage.covered_requirements,
            "missing": coverage.missing_requirements,
            "recovery_queries": coverage.additional_queries,
            "highlights": [
                f"Covered requirements: {len(coverage.covered_requirements)}",
                f"Missing requirements: {len(coverage.missing_requirements)}",
                *(
                    ["Covered: " + "; ".join(coverage.covered_requirements)]
                    if coverage.covered_requirements else []
                ),
                *(
                    ["Missing: " + "; ".join(coverage.missing_requirements)]
                    if coverage.missing_requirements else []
                ),
                *(
                    ["Recovery searches: " + "; ".join(
                        coverage.additional_queries
                    )]
                    if coverage.additional_queries else []
                ),
            ],
        })

    recovery_docs: list[Document] = []
    recovery_queries: list[str] = []
    if use_agentic_retrieval and coverage.additional_queries:
        recovery_queries = list(coverage.additional_queries)
        initial_missing_requirements = list(
            coverage.missing_requirements
        )
        recovery_start = perf_counter()
        recovery_vector_groups: list[list[Document]] = []
        recovery_bm25_groups: list[list[Document]] = []
        for recovery_query in coverage.additional_queries:
            recovery_cities = [
                city for city in comparison_cities
                if re.search(
                    rf"(?<!\w){re.escape(city)}(?!\w)",
                    recovery_query,
                    re.IGNORECASE,
                )
            ]
            recovery_filters = (
                replace(
                    filters,
                    city=recovery_cities[0] if len(recovery_cities) == 1 else None,
                    cities=recovery_cities,
                )
                if recovery_cities else filters
            )
            recovery_vector_groups.append(
                vector_search(
                    query=recovery_query,
                    filters=recovery_filters,
                    limit=min(vector_limit, 10),
                )
            )
            recovery_bm25_groups.append(
                bm25_search(
                    query=recovery_query,
                    filters=recovery_filters,
                    limit=min(bm25_limit, 10),
                )
            )

        recovery_vector = merge_unique_documents(recovery_vector_groups)
        recovery_bm25 = merge_unique_documents(recovery_bm25_groups)
        recovery_docs = merge_unique_documents([
            recovery_vector,
            recovery_bm25,
        ])
        vector_docs = merge_unique_documents([vector_docs, recovery_vector])
        bm25_docs = merge_unique_documents([bm25_docs, recovery_bm25])
        fused_docs = fuse_results(
            vector_docs=vector_docs,
            bm25_docs=bm25_docs,
            parsed=parsed,
            memory=memory,
            target_lat=target_lat,
            target_lon=target_lon,
        )
        candidates, reranked_docs, comparison_balance = _rerank_with_comparison_balance(
            query=rewritten_query,
            fused_documents=fused_docs,
            comparison_cities=comparison_cities,
            fusion_top_k=fusion_top_k,
            rerank_top_k=rerank_top_k,
        )
        timings.recovery_ms = _elapsed_ms(recovery_start)

        start = perf_counter()
        coverage = check_evidence_coverage(
            query=rewritten_query,
            requirements=plan.requirements,
            documents=reranked_docs,
            telemetry_stage="coverage_checker_recheck",
        )
        timings.checker_ms += _elapsed_ms(start)
        final_selected_ids = {
            _document_identifier(document) for document in reranked_docs
        }
        newly_covered_requirements = sorted(
            set(coverage.covered_requirements)
            - set(initial_coverage.covered_requirements)
        )
        recovery_effectiveness = {
            "performed": True,
            "queries": recovery_queries,
            "candidate_count": len(recovery_docs),
            "new_unique_candidate_count": sum(
                _document_identifier(document) not in initial_candidate_ids
                for document in recovery_docs
            ),
            "coverage_ratio_before": initial_coverage.coverage_ratio,
            "coverage_ratio_after": coverage.coverage_ratio,
            "new_selected_evidence_ids": sorted(
                final_selected_ids - initial_selected_ids
            ),
            "newly_covered_requirements": newly_covered_requirements,
            "improved": (
                coverage.coverage_ratio > initial_coverage.coverage_ratio
                or bool(newly_covered_requirements)
            ),
            "stop_reason": (
                "coverage_sufficient"
                if coverage.sufficient
                else (
                    "improved_but_incomplete"
                    if coverage.coverage_ratio > initial_coverage.coverage_ratio
                    or bool(newly_covered_requirements)
                    else "no_coverage_improvement"
                )
            ),
        }
        if progress_callback:
            progress_callback("recovery", {
                "summary": (
                    f"Retried retrieval for {len(initial_missing_requirements)} "
                    f"missing requirement{'s' if len(initial_missing_requirements) != 1 else ''}, "
                    f"adding {len(recovery_docs)} recovery candidates."
                ),
                "recovery": True,
                "recovery_candidate_count": len(recovery_docs),
                "evidence_count": len(reranked_docs),
                "comparison_balance": comparison_balance,
                "effectiveness": recovery_effectiveness,
                "highlights": [
                    *(
                        ["Missing topics searched again: " + "; ".join(
                            initial_missing_requirements
                        )]
                        if initial_missing_requirements else []
                    ),
                    f"Recovery candidates added: {len(recovery_docs)}",
                    f"Final evidence selected: {len(reranked_docs)}",
                ],
            })
            progress_callback("rechecking", {
                "summary": (
                    "The recovered evidence now covers all requested topics."
                    if coverage.sufficient
                    else "The available database still does not cover every topic."
                ),
                "sufficient": coverage.sufficient,
                "coverage_ratio": coverage.coverage_ratio,
                "requirement_assessments": [
                    item.model_dump() for item in coverage.requirement_assessments
                ],
                "covered": coverage.covered_requirements,
                "missing": coverage.missing_requirements,
                "recovery_performed": True,
                "highlights": [
                    "Recovery retrieval was performed",
                    f"Covered requirements: {len(coverage.covered_requirements)}",
                    f"Remaining missing requirements: {len(coverage.missing_requirements)}",
                    *(
                        ["Still missing: " + "; ".join(coverage.missing_requirements)]
                        if coverage.missing_requirements else []
                    ),
                ],
            })

    start = perf_counter()
    confidence = (
        evaluate_retrieval_confidence(
            reranked_docs
        )
    )
    timings.final_ms = _elapsed_ms(
        start
    )
    answer_readiness = evaluate_answer_readiness(
        parsed=parsed,
        coverage=coverage,
        documents=reranked_docs,
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
        plan=plan,
        vector_docs=vector_docs,
        bm25_docs=bm25_docs,
        fused_docs=fused_docs,
        candidates=candidates,
        reranked_docs=reranked_docs,
        recovery_docs=recovery_docs,
        recovery_queries=recovery_queries,
        confidence=confidence,
        comparison_balance=comparison_balance,
        recovery_effectiveness=recovery_effectiveness,
        answer_readiness=answer_readiness,
        initial_coverage=initial_coverage,
        coverage=coverage,
        timings=timings,
    )


def filters_to_dict(
    filters: RetrievalFilters,
) -> dict:
    return asdict(filters)
