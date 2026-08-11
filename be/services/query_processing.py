from __future__ import annotations

import json
from typing import Any

from schemas.pipeline import ParsedQuery

from config.vocab import (
    ALLOWED_ACTIVITIES,
    ALLOWED_PLACE_TYPES,
    ALLOWED_SUITABLE_FOR,
    ALLOWED_TRAVEL_STYLES,
)
from data_building.extract_metadata.extractor import (
    DEEPSEEK_METADATA_MODEL,
    get_deepseek_client,
)
from db.full_model import RagChunkORM
from db.session import SessionLocal


def rewrite_query(
    query: str,
    conversation_history: list[dict[str, Any]],
    model: str = DEEPSEEK_METADATA_MODEL,
) -> str:
    """
    Notebook logic moved into a reusable service.
    """
    query = query.strip()

    if not query:
        raise ValueError("Query cannot be empty")

    if not conversation_history:
        return query

    deepseek_client = get_deepseek_client()
    recent_history = conversation_history[-6:]

    history_text = "\n".join(
        f"{item.get('role', 'unknown')}: "
        f"{item.get('content', '')}"
        for item in recent_history
    )

    system_msg = """
You are a query rewriting system for a tourism RAG application.

Rewrite the user's latest query into a clear standalone retrieval query
using recent conversation history.

Rules:
- Resolve references such as "there", "that place", "it", and "those".
- Preserve the original intent.
- Preserve explicit locations, dates, duration, budget, travel style,
  activities, and constraints.
- Use history only to resolve missing context.
- Do not invent preferences or facts.
- Do not answer the question.
- Keep the query concise.
- If already standalone, keep it mostly unchanged.

Return valid JSON only:
{
  "rewritten_query": "standalone retrieval query"
}
""".strip()

    user_prompt = f"""
Conversation history:
{history_text}

Current user query:
{query}

Return the rewritten query as JSON.
""".strip()

    try:
        response = deepseek_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_msg,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0,
            max_tokens=300,
            response_format={
                "type": "json_object",
            },
        )

        raw_text = response.choices[0].message.content

        if not raw_text or not raw_text.strip():
            return query

        result = json.loads(raw_text)
        rewritten = result.get("rewritten_query")

        return (
            rewritten.strip()
            if rewritten
            else query
        )

    except Exception as exc:
        print(
            f"[QUERY REWRITE WARNING] {exc}"
        )
        return query


def get_known_cities() -> list[str]:
    db = SessionLocal()

    try:
        rows = (
            db.query(RagChunkORM.city)
            .filter(RagChunkORM.city.isnot(None))
            .filter(RagChunkORM.city != "")
            .distinct()
            .order_by(RagChunkORM.city)
            .all()
        )

        return [
            row[0]
            for row in rows
            if row[0]
        ]

    finally:
        db.close()


def build_query_parser_prompt(
    known_cities: list[str],
) -> str:
    return f"""
Extract travel retrieval metadata from the user query.

Return JSON only.

Cities: {", ".join(known_cities)}
Place types: {", ".join(ALLOWED_PLACE_TYPES)}
Activities: {", ".join(ALLOWED_ACTIVITIES)}
Travel styles: {", ".join(ALLOWED_TRAVEL_STYLES)}
Suitable for: {", ".join(ALLOWED_SUITABLE_FOR)}

Intent:
itinerary, recommendation, attraction_search,
accommodation_search, food_search, transport,
event_search, travel_information

Rules:
- Use only values from the lists.
- City must exactly match a listed city.
- Only extract information stated or strongly implied by the query.
- Do not infer preferences from the destination itself.
- Unknown scalar = null.
- Unknown list = [].

JSON:
{{
  "intent": null,
  "location": {{
    "country": null,
    "city": null,
    "province": null
  }},
  "place_types": [],
  "activities": [],
  "travel_styles": [],
  "suitable_for": [],
  "constraints": {{
    "budget": null,
    "duration_days": null,
    "date_from": null,
    "date_to": null,
    "near_place": null,
    "max_distance_km": null
  }}
}}
""".strip()


def parse_query_deepseek(
    query: str,
    model: str = DEEPSEEK_METADATA_MODEL,
) -> ParsedQuery:
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    known_cities = get_known_cities()
    system_msg = build_query_parser_prompt(
        known_cities
    )
    deepseek_client = get_deepseek_client()

    response = deepseek_client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_msg,
            },
            {
                "role": "user",
                "content": query.strip(),
            },
        ],
        temperature=0,
        max_tokens=300,
        response_format={
            "type": "json_object",
        },
    )

    raw_text = response.choices[0].message.content

    if not raw_text or not raw_text.strip():
        raise ValueError(
            "DeepSeek returned empty query parsing result"
        )

    parsed_json = json.loads(raw_text)
    parsed = ParsedQuery.model_validate(
        parsed_json
    )

    if (
        parsed.location.city
        and parsed.location.city not in known_cities
    ):
        print(
            "[QUERY PARSER WARNING] "
            f"Invalid city returned: {parsed.location.city}"
        )
        parsed.location.city = None

    parsed.place_types = [
        value
        for value in parsed.place_types
        if value in ALLOWED_PLACE_TYPES
    ]

    parsed.activities = [
        value
        for value in parsed.activities
        if value in ALLOWED_ACTIVITIES
    ]

    parsed.travel_styles = [
        value
        for value in parsed.travel_styles
        if value in ALLOWED_TRAVEL_STYLES
    ]

    parsed.suitable_for = [
        value
        for value in parsed.suitable_for
        if value in ALLOWED_SUITABLE_FOR
    ]

    return parsed


def parse_query(
    query: str,
) -> ParsedQuery:
    try:
        return parse_query_deepseek(
            query
        )
    except Exception as exc:
        # Same safe fallback as the notebook:
        # retrieval still runs when the semantic parser fails.
        print(
            f"[QUERY PARSER WARNING] {exc}"
        )
        return ParsedQuery(
            intent="travel_information"
        )
