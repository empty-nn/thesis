from __future__ import annotations

import json

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
    EvidenceItem,
)
from services.pipeline_runner import (
    run_retrieval_pipeline,
)
from services.retrieval import (
    source_name,
)
from services.conversation_memory import get_conversation_memory


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
    model: str = DEEPSEEK_METADATA_MODEL,
) -> str:
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
- For an itinerary, organize the answer by day.
- For recommendations, give a ranked or grouped recommendation.
- For a factual question, answer it directly.
- Use the user's preferences only when relevant.
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

Retrieved evidence:
{evidence_text or "No evidence was retrieved."}

Generate the best final answer for the user.
""".strip()

    client = get_deepseek_client()
    response = client.chat.completions.create(
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
) -> ChatResponse:
    history = [
        item.model_dump()
        for item
        in request.conversation_history
    ]

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
        )
    )

    evidence = build_evidence(
        artifacts.reranked_docs
    )

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
    )

    return ChatResponse(
        answer=answer,
        sources=_chat_sources(
            evidence
        ),
    )
