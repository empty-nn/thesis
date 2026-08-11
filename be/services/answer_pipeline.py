from __future__ import annotations

import json
from typing import Any, Callable

from data_building.extract_metadata.extractor import (
    DEEPSEEK_METADATA_MODEL,
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
    model: str = DEEPSEEK_METADATA_MODEL,
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
        }

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
