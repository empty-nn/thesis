from __future__ import annotations

import json
from typing import Any, Callable

from data_building.extract_metadata.extractor import (
    DEEPSEEK_ANSWER_MODEL,
    get_deepseek_client,
)
from schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSource,
)
from schemas.pipeline import (
    AnswerReadiness,
    EvidenceItem,
)
from services.pipeline_runner import (
    run_retrieval_pipeline,
)
from services.retrieval import (
    source_name,
)
from services.conversation_memory import get_conversation_memory
from services.request_routing import classify_request
from services.llm_telemetry import create_chat_completion
from services.external_web_fallback import (
    classify_external_requirements,
    external_web_max_requirements,
    generate_external_web_answer,
)


def build_evidence(documents) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []

    for index, doc in enumerate(documents, start=1):
        evidence.append(
            EvidenceItem(
                evidence_id=f"E{index}",
                chunk_id=doc.metadata[
                    "chunk_id"
                ],
                document_id=(
                    doc.metadata.get(
                        "document_id"
                    )
                ),
                place_name=(
                    doc.metadata.get(
                        "place_name"
                    )
                ),
                content=doc.page_content,
                metadata=doc.metadata,
            )
        )

    return evidence


def generate_answer(
    query: str,
    rewritten_query: str,
    parsed,
    evidence: list[EvidenceItem],
    conversation_history: list[dict],
    memory,
    conversation_memory=None,
    coverage=None,
    answer_readiness: AnswerReadiness | None = None,
    model: str = DEEPSEEK_ANSWER_MODEL,
) -> str:
    if answer_readiness is not None and answer_readiness.mode == "insufficient":
        missing = (
            "; ".join(coverage.missing_requirements)
            if coverage is not None and coverage.missing_requirements
            else query
        )
        return (
            "I couldn't find enough cited evidence in the current travel database "
            f"to answer this request reliably: **{missing}**. I don't want to fill "
            "the missing parts with unsupported details."
        )
    evidence_text = "\n\n".join(
        (
            f"[{item.evidence_id}]\n"
            f"Place: {item.place_name or 'Unknown'}\n"
            f"Source: {item.metadata.get('source_location') or 'Unknown'}\n"
            f"Content:\n{item.content}"
        )
        for item in evidence
    )

    history_text = "\n".join(
        f"{message.get('role', 'unknown')}: "
        f"{message.get('content', '')}"
        for message in conversation_history[-6:]
    )

    system_prompt = """
You are a personalized Vietnam travel assistant.

Answer the user's question using the provided retrieved evidence.

Rules:
- Base factual travel claims on the provided evidence.
- Do not invent places, prices, opening hours, distances, or facts.
- If the evidence is insufficient, say so clearly.
- Answer naturally instead of copying the evidence.
- Adapt the response to the parsed intent.
- Treat explicit_constraints as mandatory user requirements.
- Treat location, place_types, activities, travel_styles, and suitable_for as retrieval
  facets: they help find evidence but must not be presented as stated user preferences
  unless also supported by explicit_constraints, memory, or conversation context.
- For an itinerary, organize the answer by day only when answer readiness is complete.
- For recommendations, give a ranked or grouped recommendation.
- For a factual question, answer it directly.
- Use the user's preferences only when relevant.
- Match detail and terminology to the user's expertise.
- Follow answer_length, tone, and explanation_style when supplied.
- Use interests, preferred travel styles, and preferred activities only when relevant.
- Respect budget_level, avoid items, and durable constraints.
- Treat allergies and dietary exclusions as safety-critical constraints. Never
  describe a dish as safe, allergy-safe, shellfish-free, or a "safe bet"
  unless the evidence explicitly verifies the relevant ingredients and
  cross-contact risk for that preparation.
- When allergy evidence is incomplete, say that a dish may be easier to adapt,
  not that it is safe. Tell the user to verify broth or stock, sauces, fillings,
  garnishes, cooking oil or utensils, and cross-contact with the vendor.
- Do not infer absence of shellfish from a generic dish name or base recipe.
- Use personal facts only when they materially help; never mention stored memory or profiling.
- Use the current conversation trip state for this chat only; do not treat it as a permanent preference.
- Cite factual claims with evidence IDs such as [E1] or [E1][E2].
- Use only evidence IDs that appear in the retrieved evidence.
- Do not mention retrieval, chunks, vector search, BM25, or internal systems.
""".strip()

    user_prompt = f"""
Original user query:
{query}

Standalone retrieval query:
{rewritten_query}

Parsed query:
{json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2)}

User memory:
{json.dumps(memory.model_dump(), ensure_ascii=False, indent=2)}

Current conversation trip state:
{json.dumps(
    conversation_memory.model_dump()
    if conversation_memory is not None
    else {},
    ensure_ascii=False,
    indent=2,
)}

Recent conversation:
{history_text or "None"}

Evidence coverage:
{json.dumps(
    coverage.model_dump() if coverage is not None else {},
    ensure_ascii=False,
    indent=2,
)}

Answer readiness (mandatory response mode):
{json.dumps(
    answer_readiness.model_dump() if answer_readiness is not None else {},
    ensure_ascii=False,
    indent=2,
)}

Retrieved evidence:
{evidence_text or "No evidence was retrieved."}

Generate the best final answer for the user.
If answer readiness is partial, provide only supported stops or facts and do
not present the result as a complete multi-day itinerary.
If coverage is incomplete, answer only the covered requirements and clearly
state which requested information is unavailable. Never fill missing parts
using unsupported assumptions.
""".strip()

    client = get_deepseek_client()
    response = create_chat_completion(
        "answer_generation", client,
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.2,
        max_tokens=1200,
    )

    content = response.choices[0].message.content

    if not content or not content.strip():
        raise ValueError(
            "DeepSeek returned an empty answer"
        )

    return content.strip()


def _chat_sources(
    evidence: list[EvidenceItem],
) -> list[ChatSource]:
    result: list[
        ChatSource
    ] = []

    for item in evidence:
        url = item.metadata.get(
            "source_location"
        )

        result.append(
            ChatSource(
                id=item.evidence_id,
                title=(
                    item.place_name
                    or source_name(url)
                ),
                url=url,
            )
        )

    return result


def run_chat_pipeline(
    request: ChatRequest,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> ChatResponse:
    history = [
        item.model_dump()
        for item
        in request.conversation_history
    ]

    route = classify_request(request.message, history)
    if progress_callback:
        progress_callback("classification", {
            "summary": (
                f"Classified this as a {route.category.replace('_', ' ')} request."
            ),
            "category": route.category,
            "confidence": route.confidence,
            "reason": route.reason,
            "highlights": [
                f"Category: {route.category.replace('_', ' ')}",
                f"Decision: {'continue to travel retrieval' if route.category == 'travel' else 'skip retrieval'}",
                *([f"Reason: {route.reason}"] if route.reason else []),
            ],
        })

    if route.category == "out_of_scope":
        return ChatResponse(
            answer=(
                "I’m designed to help with Vietnam travel planning, "
                "destinations, activities, accommodation, food, and transport. "
                "Please ask me a travel-related question."
            ),
            route_category="out_of_scope",
        )

    if route.category == "ambiguous":
        return ChatResponse(
            answer=(
                route.clarification_question
                or "Could you clarify what travel destination or trip information you mean?"
            ),
            route_category="ambiguous",
        )

    conversation_memory = get_conversation_memory(
        user_id=request.user_id,
        conversation_id=request.conversation_id,
    )

    retrieval_history = history[-5:]
    if conversation_memory.summary:
        retrieval_history = [
            *retrieval_history,
            {
                "role": "system",
                "content": (
                    "Current conversation trip context: "
                    + json.dumps(
                        conversation_memory.model_dump(),
                        ensure_ascii=False,
                    )
                ),
            },
        ]

    artifacts = (
        run_retrieval_pipeline(
            query=request.message,
            conversation_history=retrieval_history,
            user_id=request.user_id,
            progress_callback=progress_callback,
        )
    )

    evidence = build_evidence(
        artifacts.reranked_docs
    )

    knowledge_gap = None
    if not artifacts.coverage.sufficient:
        knowledge_gap = {
            "query": request.message,
            "rewritten_query": artifacts.rewritten_query,
            "missing_requirements": artifacts.coverage.missing_requirements,
            "recovery_queries": artifacts.recovery_queries,
            "top_evidence": [
                {
                    "chunk_id": str(doc.metadata.get("chunk_id")),
                    "place_name": doc.metadata.get("place_name"),
                    "source_location": doc.metadata.get("source_location"),
                }
                for doc in artifacts.reranked_docs[:8]
            ],
            "external_sources": [],
            "external_recovery": {
                "status": "not_attempted",
                "answer_generated": False,
            },
            "ingestion_status": "pending_review",
        }

    external_web_result = None
    if not artifacts.coverage.sufficient:
        external_requirements = classify_external_requirements(
            artifacts.coverage.missing_requirements
        )
        searchable_requirements = [
            item for item in external_requirements if item.search_eligible
        ]
        recent_age_limits = sorted({
            item.max_age_days
            for item in searchable_requirements
            if item.max_age_days is not None
        })
        maximum_external_requirements = external_web_max_requirements()
        needs_clarification = (
            len(searchable_requirements) > maximum_external_requirements
        )
        if progress_callback and needs_clarification:
            progress_callback("external_search", {
                "summary": (
                    f"External search was paused because the request contains "
                    f"{len(searchable_requirements)} time-sensitive requirements; "
                    f"the configured limit is {maximum_external_requirements}."
                ),
                "missing_requirements": [
                    item.requirement for item in searchable_requirements
                ],
                "highlights": [
                    "No external API call was made",
                    "Response type: clarification menu",
                    "Unselected requirements remain recorded for later turns",
                ],
            })
        elif progress_callback and searchable_requirements:
            progress_callback("external_search", {
                "summary": (
                    "Searching current external sources for time-sensitive "
                    "requirements still missing after database recovery."
                ),
                "missing_requirements": [
                    item.requirement for item in searchable_requirements
                ],
                "highlights": [
                    "Trigger: internal evidence remained incomplete",
                    (
                        "Freshness classes: "
                        + ", ".join(sorted({
                            item.freshness_class
                            for item in searchable_requirements
                        }))
                    ),
                    *(
                        [
                            "Recent-source maximum age: "
                            + ", ".join(map(str, recent_age_limits))
                            + " day(s)"
                        ]
                        if recent_age_limits
                        else []
                    ),
                    "Returned URLs will be queued for later review",
                ],
            })
        elif progress_callback:
            progress_callback("external_search", {
                "summary": (
                    "External search was skipped because the remaining gaps "
                    "were stable topics rather than time-sensitive information."
                ),
                "missing_requirements": artifacts.coverage.missing_requirements,
                "highlights": [
                    "No external API call was made",
                    "Stable gaps remain queued for corpus review",
                ],
            })
        external_web_result = generate_external_web_answer(
            query=request.message,
            rewritten_query=artifacts.rewritten_query,
            missing_requirements=artifacts.coverage.missing_requirements,
            evidence=evidence,
            parsed=artifacts.parsed,
            memory=artifacts.memory,
            conversation_memory=conversation_memory,
            requirements=external_requirements,
        )
        if knowledge_gap is not None:
            source_urls = [
                source.url for source in external_web_result.sources if source.url
            ]
            source_date_metadata_available = any(
                source.freshness_metadata_status in {"available", "live_feed"}
                for source in external_web_result.sources
            )
            knowledge_gap["external_sources"] = [
                source.to_storage_dict() for source in external_web_result.sources
            ]
            knowledge_gap["external_recovery"] = {
                "status": external_web_result.status,
                "model": external_web_result.model,
                "answer_generated": external_web_result.succeeded,
                "source_count": len(external_web_result.sources),
                "cited_source_count": sum(
                    source.cited_in_answer for source in external_web_result.sources
                ),
                "error_type": external_web_result.error_type,
                "maximum_requirements_per_call": maximum_external_requirements,
                "clarification_options": external_web_result.clarification_options,
                "requirements": [
                    {
                        **requirement.to_storage_dict(),
                        "internal_status": "not_fully_covered",
                        "review_status": "pending_review",
                        "external_search_status": (
                            external_web_result.status
                            if requirement.search_eligible
                            else "skipped_stable_requirement"
                        ),
                        "freshness_validation": (
                            (
                                "not_attempted_clarification_required"
                                if external_web_result.status == "clarification_required"
                                else
                                "source_date_metadata_available_pending_review"
                                if source_date_metadata_available
                                else "prompt_constrained_source_date_unverified"
                            )
                            if requirement.search_eligible
                            else "not_required"
                        ),
                        "candidate_source_urls": (
                            source_urls if requirement.search_eligible else []
                        ),
                    }
                    for requirement in external_web_result.requirements
                ],
            }

        if external_web_result.status == "clarification_required":
            return ChatResponse(
                answer=(
                    external_web_result.clarification_question
                    or "Please choose which current-information requirement to check first."
                ),
                knowledge_gap=knowledge_gap,
            )

        if external_web_result.succeeded:
            cited_sources = [
                source for source in external_web_result.sources
                if source.cited_in_answer
            ] or external_web_result.sources[:8]
            if progress_callback:
                progress_callback("external_search", {
                    "summary": (
                        f"Generated a web-grounded fallback using "
                        f"{len(cited_sources)} cited source(s)."
                    ),
                    "status": external_web_result.status,
                    "source_count": len(external_web_result.sources),
                    "cited_source_count": len(cited_sources),
                    "highlights": [
                        f"Consulted URLs recorded: {len(external_web_result.sources)}",
                        f"Cited URLs returned: {len(cited_sources)}",
                        "Corpus ingestion status: pending review",
                    ],
                })
            return ChatResponse(
                answer=external_web_result.answer or "",
                sources=[
                    *_chat_sources(evidence),
                    *[
                        ChatSource(id=source.id, title=source.title, url=source.url)
                        for source in cited_sources
                    ],
                ],
                knowledge_gap=knowledge_gap,
            )
        if progress_callback and external_web_result.status != (
            "skipped_no_time_sensitive_requirements"
        ):
            failure_messages = {
                "disabled": "External search is disabled by configuration.",
                "unavailable": "External search is unavailable because no OpenAI API key is configured.",
                "completed_without_sources": "The external answer had no acceptable cited source.",
                "completed_empty_answer": "The external search returned sources but no final answer.",
                "incomplete_max_output_tokens": (
                    "The external search reached its output-token limit before producing a final answer."
                ),
            }
            failure_summary = failure_messages.get(
                external_web_result.status,
                (
                    "External web evidence was unavailable "
                    f"({external_web_result.status})."
                ),
            )
            progress_callback("external_search", {
                "summary": (
                    failure_summary + " The response remains limited to "
                    "verified internal evidence."
                ),
                "status": external_web_result.status,
                "source_count": len(external_web_result.sources),
                "highlights": [
                    f"Fallback status: {external_web_result.status}",
                    "No unsupported web answer was returned",
                    "The knowledge gap remains queued for review",
                ],
            })

    if (
        not artifacts.coverage.sufficient
        and not artifacts.coverage.covered_requirements
    ):
        if progress_callback:
            progress_callback("generating", {
                "summary": (
                    "Normal answer generation was blocked because no requested "
                    "topic had sufficient evidence."
                ),
                "highlights": [
                    "Evidence gate: blocked",
                    "Response type: transparent database-gap notice",
                    "The missing request was queued for later data improvement",
                ],
            })
        missing_text = "; ".join(
            artifacts.coverage.missing_requirements
        ) or request.message
        return ChatResponse(
            answer=(
                "I couldn’t find sufficient information in the current travel "
                f"database for: **{missing_text}**. I don’t want to provide "
                "unsupported details. This missing topic has been recorded so "
                "the travel data can be improved later."
            ),
            knowledge_gap=knowledge_gap,
        )

    if progress_callback:
        evidence_places = list(dict.fromkeys(
            item.place_name
            for item in evidence
            if item.place_name
        ))[:5]
        progress_callback("generating", {
            "summary": (
                f"Generating the final answer from {len(evidence)} "
                "selected evidence items."
            ),
            "evidence_count": len(evidence),
            "evidence_ids": [item.evidence_id for item in evidence],
            "answer_readiness": artifacts.answer_readiness.model_dump(),
            "highlights": [
                f"Evidence available: {len(evidence)} items",
                "Citation IDs: " + ", ".join(
                    item.evidence_id for item in evidence
                ),
                *(
                    ["Evidence places: " + ", ".join(evidence_places)]
                    if evidence_places else []
                ),
                "Answer rules: evidence-grounded, personalized, and cited",
            ],
        })

    answer = generate_answer(
        query=request.message,
        rewritten_query=(
            artifacts.rewritten_query
        ),
        parsed=artifacts.parsed,
        evidence=evidence,
        conversation_history=history,
        memory=artifacts.memory,
        conversation_memory=conversation_memory,
        coverage=artifacts.coverage,
        answer_readiness=artifacts.answer_readiness,
    )

    return ChatResponse(
        answer=answer,
        sources=_chat_sources(
            evidence
        ),
        knowledge_gap=knowledge_gap,
    )
