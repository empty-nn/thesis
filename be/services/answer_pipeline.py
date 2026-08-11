from __future__ import annotations

from schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSource,
)
from schemas.pipeline import (
    EvidenceItem,
    ItineraryDay,
    ItineraryStop,
    StructuredItinerary,
)
from services.pipeline_runner import (
    run_retrieval_pipeline,
)
from services.retrieval import (
    source_name,
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


def draft_itinerary_mock(
    parsed,
    evidence: list[EvidenceItem],
) -> StructuredItinerary:
    """
    This intentionally remains the notebook's mock drafting step.

    Replace this function later with an evidence-grounded DeepSeek generation
    call. Retrieval and debugging are already productionized; generation is
    not silently invented here because it was not implemented in the notebook.
    """
    number_of_days = (
        parsed.constraints.duration_days
        or 1
    )

    destination = (
        parsed.location.city
    )

    days: list[ItineraryDay] = []

    evidence_index = 0

    for day_number in range(
        1,
        number_of_days + 1,
    ):
        stops: list[
            ItineraryStop
        ] = []

        for _ in range(2):
            if (
                evidence_index
                >= len(evidence)
            ):
                break

            item = evidence[
                evidence_index
            ]
            evidence_index += 1

            stops.append(
                ItineraryStop(
                    place_name=(
                        item.place_name
                        or "Recommended place"
                    ),
                    evidence_ids=[
                        item.evidence_id
                    ],
                )
            )

        days.append(
            ItineraryDay(
                day=day_number,
                stops=stops,
            )
        )

    return StructuredItinerary(
        destination=destination,
        days=days,
    )


def render_itinerary(
    itinerary: StructuredItinerary,
) -> str:
    lines: list[str] = []

    if itinerary.destination:
        lines.append(
            f"## Trip to {itinerary.destination}"
        )
    else:
        lines.append(
            "## Travel recommendations"
        )

    for day in itinerary.days:
        lines.append(
            f"\n### Day {day.day}"
        )

        if not day.stops:
            lines.append(
                "- No sufficiently ranked evidence was returned."
            )

        for stop in day.stops:
            citation_text = ""

            if stop.evidence_ids:
                citation_text = (
                    " ["
                    + ", ".join(
                        stop.evidence_ids
                    )
                    + "]"
                )

            lines.append(
                f"- **{stop.place_name}**"
                f"{citation_text}"
            )

    return "\n".join(
        lines
    )


def _chat_sources(
    evidence: list[EvidenceItem],
) -> list[ChatSource]:
    result: list[
        ChatSource
    ] = []

    seen: set[str] = set()

    for item in evidence:
        url = item.metadata.get(
            "source_location"
        )

        source_id = (
            item.document_id
            or item.chunk_id
        )

        if source_id in seen:
            continue

        seen.add(source_id)

        result.append(
            ChatSource(
                id=source_id,
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

    artifacts = (
        run_retrieval_pipeline(
            query=request.message,
            conversation_history=history,
            user_id=request.user_id,
        )
    )

    evidence = build_evidence(
        artifacts.reranked_docs
    )

    itinerary = (
        draft_itinerary_mock(
            parsed=artifacts.parsed,
            evidence=evidence,
        )
    )

    answer = render_itinerary(
        itinerary
    )

    return ChatResponse(
        answer=answer,
        sources=_chat_sources(
            evidence
        ),
    )
