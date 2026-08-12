from __future__ import annotations

import json
import re
from typing import Any

from schemas.pipeline import ExplicitConstraint, ParsedQuery

from config.vocab import (
    ALLOWED_ACTIVITIES,
    ALLOWED_BUDGET_LEVELS,
    ALLOWED_REGIONS,
    ALLOWED_PLACE_TYPES,
    ALLOWED_QUERY_INTENTS,
    ALLOWED_QUERY_OPERATIONS,
    ALLOWED_SUITABLE_FOR,
    ALLOWED_TRAVEL_STYLES,
    REGION_ALIASES,
)
from data_building.extract_metadata.extractor import (
    DEEPSEEK_FAST_MODEL,
    DEEPSEEK_PARSER_MODEL,
    get_deepseek_client,
)
from db.full_model import RagChunkORM
from db.session import SessionLocal
from services.llm_telemetry import create_chat_completion


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _resolve_terminal_stay_followup(
    query: str,
    conversation_history: list[dict[str, Any]],
) -> str | None:
    """Resolve 'final N nights' to the trip's explicitly stated end city."""
    if not re.search(
        r"\b(where\s+(?:should|can)\s+i\s+(?:stay|base)|base myself|"
        r"accommodation|hotel|hostel)\b",
        query,
        re.IGNORECASE,
    ):
        return None
    nights_match = re.search(
        r"\b(?:final|last)\s+(\d+|one|two|three|four|five|six|seven|eight|"
        r"nine|ten)\s+nights?\b",
        query,
        re.IGNORECASE,
    )
    if not nights_match:
        return None
    raw_nights = nights_match.group(1).casefold()
    nights = int(raw_nights) if raw_nights.isdigit() else _NUMBER_WORDS[raw_nights]
    history_text = "\n".join(
        str(item.get("content") or "") for item in conversation_history
    )
    try:
        known_cities = get_known_cities()
    except Exception as exc:
        print(f"[QUERY REWRITE LOCATION WARNING] {exc}")
        return None
    terminal_city = next(
        (
            city
            for city in sorted(known_cities, key=len, reverse=True)
            if re.search(
                rf"\b(?:end(?:ing|s|ed)?|finish(?:ing|es|ed)?)\s+in\s+"
                rf"{re.escape(city)}(?!\w)",
                history_text,
                re.IGNORECASE,
            )
        ),
        None,
    )
    if not terminal_city:
        return None
    itinerary_kind = (
        "photography itinerary"
        if re.search(r"\bphotograph(?:y|ic|er)?\b", history_text, re.IGNORECASE)
        else "itinerary"
    )
    return (
        f"Where should I stay in {terminal_city} for the final {nights} nights "
        f"of the existing {itinerary_kind}?"
    )


def rewrite_query(
    query: str,
    conversation_history: list[dict[str, Any]],
    model: str = DEEPSEEK_FAST_MODEL,
) -> str:
    """
    Notebook logic moved into a reusable service.
    """
    query = query.strip()

    if not query:
        raise ValueError("Query cannot be empty")

    if not conversation_history:
        return query

    terminal_stay_query = _resolve_terminal_stay_followup(
        query, conversation_history
    )
    if terminal_stay_query:
        return terminal_stay_query

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
- Do not copy unrelated constraints from earlier turns. Carry a prior
  constraint only when it is needed to resolve the current reference.
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
        response = create_chat_completion(
            "query_rewrite", deepseek_client,
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
Budget levels: {", ".join(ALLOWED_BUDGET_LEVELS)}
Regions: {", ".join(ALLOWED_REGIONS)}

Intent: {", ".join(ALLOWED_QUERY_INTENTS)}
Operation: {", ".join(ALLOWED_QUERY_OPERATIONS)}

Rules:
- Use only values from the lists.
- Intent identifies the travel task/domain; operation identifies how to handle it.
- Comparing transport modes is intent=transport, operation=compare.
- Comparing destinations is intent=recommendation, operation=compare.
- explicit_constraints contains only facts directly stated in this standalone
  query or resolved by the conversation rewrite. Use key/value objects and only
  these keys: country, region, city, province, place_type, activity, travel_style,
  suitable_for, budget, duration_days, date_from, date_to, near_place,
  max_distance_km. Every value must be a JSON string.
- Every explicit constraint must use exactly this shape:
  {{"key": "city", "value": "Hue"}}. Never return shorthand such as
  {{"city": "Hue"}}.
- Northern Vietnam, Central Vietnam, and Southern Vietnam are regions, never
  provinces. Preserve their canonical value in location.region. Do not invent
  a city when only a region is stated.
- Geographic names belong in country/region/city/province constraints; do not also
  emit place_type=country, place_type=city, place_type=province, or
  place_type=region.
- "solo" or "traveling alone" maps to suitable_for=solo_travelers, never to a
  travel_style.
- Prefer the single most direct label. Do not encode the same phrase as both an
  activity and a travel_style unless the query explicitly states both meanings.
- Do not convert interests or activities into suitable_for labels in
  explicit_constraints. Do not add broader related activities. Retrieval fields
  may contain closely related search facets, but inferred facets must not appear
  in explicit_constraints.
- Budget must be one of the listed budget levels or null.
- A negated or avoided budget phrase is not a positive budget. For example,
  "without luxury prices" and "avoid luxury hotels" must not produce
  budget=luxury.
- Every city must exactly match a listed city. Use cities for comparison or multi-city queries;
  city contains the first or primary city for backward compatibility.
- Only extract information stated or strongly implied by the query.
- Do not infer preferences from the destination itself.
- Unknown scalar = null.
- Unknown list = [].

JSON:
{{
  "intent": null,
  "operation": "lookup",
  "explicit_constraints": [
    {{"key": "city", "value": "Hue"}},
    {{"key": "duration_days", "value": "3"}}
  ],
  "location": {{
    "country": null,
    "region": null,
    "city": null,
    "cities": [],
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
    model: str = DEEPSEEK_PARSER_MODEL,
) -> ParsedQuery:
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    known_cities = get_known_cities()
    system_msg = build_query_parser_prompt(
        known_cities
    )
    deepseek_client = get_deepseek_client()

    response = create_chat_completion(
        "query_parser", deepseek_client,
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
        max_tokens=600,
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
    parsed.raw_intent = parsed.intent
    parsed.raw_operation = parsed.operation

    # Do not let the LLM silently drop explicitly named destinations. This is
    # especially important for comparison and multi-city queries, where the
    # legacy singular `city` field is otherwise easy for a model to misuse.
    def is_embedded_in_named_place(city: str) -> bool:
        for match in re.finditer(
            rf"(?<!\w){re.escape(city)}(?!\w)", query, re.IGNORECASE
        ):
            suffix = query[match.end():]
            next_word = re.match(r"\s+([A-ZÀ-Ỹ][\wÀ-ỹ'-]*)", suffix)
            if not next_word or next_word.group(1).casefold() in {"city", "province"}:
                return False
        return True

    explicit_cities = [
        city for city in known_cities
        if re.search(rf"(?<!\w){re.escape(city)}(?!\w)", query, re.IGNORECASE)
        and not is_embedded_in_named_place(city)
    ]
    # Explicit names are deterministic ground truth for location filtering.
    # If none are present, retain the model's contextual resolution (useful for
    # follow-up turns whose rewritten query supplies the destination).
    if explicit_cities:
        parsed.location.cities = explicit_cities
        existing_explicit_cities = {
            item.value
            for item in parsed.explicit_constraints
            if item.key == "city"
        }
        parsed.explicit_constraints.extend(
            ExplicitConstraint(key="city", value=city)
            for city in explicit_cities
            if city not in existing_explicit_cities
        )

    def add_explicit_constraint(key: str, value: str) -> None:
        if not any(
            item.key == key and item.value == value
            for item in parsed.explicit_constraints
        ):
            parsed.explicit_constraints.append(
                ExplicitConstraint(key=key, value=value)
            )

    if re.search(r"(?<!\w)Vietnam(?!\w)", query, re.IGNORECASE):
        add_explicit_constraint("country", "Vietnam")
    normalized_query = " ".join(query.casefold().split())
    matched_region = next(
        (
            canonical
            for alias, canonical in sorted(
                REGION_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
            )
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_query)
        ),
        None,
    )
    if matched_region:
        parsed.location.region = matched_region
        add_explicit_constraint("region", matched_region)
        parsed.location.province = None
        parsed.explicit_constraints = [
            item for item in parsed.explicit_constraints
            if not (
                item.key == "province"
                and item.value.casefold() in REGION_ALIASES
            )
        ]
    if re.search(
        r"\b(solo|travel(?:ing|ling)? alone|on my own)\b",
        query,
        re.IGNORECASE,
    ):
        add_explicit_constraint("suitable_for", "solo_travelers")
    budget_phrases = {
        "mid_range": r"\b(mid[- ]range|moderate budget)\b",
        "budget": r"\b(budget|low[- ]cost|cheap)\b",
        "luxury": r"\b(luxury|high[- ]end)\b",
    }
    def has_positive_match(pattern: str) -> bool:
        for match in re.finditer(pattern, query, re.IGNORECASE):
            prefix = query[max(0, match.start() - 60):match.start()]
            if not re.search(
                r"\b(?:avoid|avoiding|without|not|no|rather than|don't want|do not want)"
                r"(?:\s+\w+){0,5}\s*$",
                prefix,
                re.IGNORECASE,
            ):
                return True
        return False
    for budget_value, pattern in budget_phrases.items():
        if has_positive_match(pattern):
            add_explicit_constraint("budget", budget_value)
        else:
            parsed.explicit_constraints = [
                item for item in parsed.explicit_constraints
                if not (item.key == "budget" and item.value == budget_value)
            ]
            if parsed.constraints.budget == budget_value:
                parsed.constraints.budget = None

    invalid_cities = [
        city for city in parsed.location.cities
        if city not in known_cities
    ]
    if invalid_cities:
        print(
            "[QUERY PARSER WARNING] "
            f"Invalid cities returned: {invalid_cities}"
        )
    parsed.location.cities = [
        city for city in parsed.location.cities
        if city in known_cities
    ]
    parsed.location.city = (
        parsed.location.cities[0]
        if parsed.location.cities else None
    )

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

    explicit_vocabularies = {
        "city": set(known_cities),
        "region": set(ALLOWED_REGIONS),
        "place_type": set(ALLOWED_PLACE_TYPES),
        "activity": set(ALLOWED_ACTIVITIES),
        "travel_style": set(ALLOWED_TRAVEL_STYLES),
        "suitable_for": set(ALLOWED_SUITABLE_FOR),
        "budget": set(ALLOWED_BUDGET_LEVELS),
    }
    allowed_explicit_keys = {
        "country", "region", "city", "province", "place_type", "activity",
        "travel_style", "suitable_for", "budget", "duration_days",
        "date_from", "date_to", "near_place", "max_distance_km",
    }
    valid_explicit_constraints: list[ExplicitConstraint] = []
    seen_explicit_constraints: set[tuple[str, str]] = set()
    for item in parsed.explicit_constraints:
        key = item.key.strip()
        value = item.value.strip()
        allowed_values = explicit_vocabularies.get(key)
        if (
            key not in allowed_explicit_keys
            or not value
            or (
                key == "place_type"
                and value in {"country", "city", "province", "region"}
            )
            or (allowed_values is not None and value not in allowed_values)
            or (key, value) in seen_explicit_constraints
        ):
            continue
        seen_explicit_constraints.add((key, value))
        valid_explicit_constraints.append(
            ExplicitConstraint(key=key, value=value)
        )
    parsed.explicit_constraints = valid_explicit_constraints

    # Explicit constraints are mandatory, so ensure retrieval sees them too.
    # The reverse direction is intentionally forbidden: inferred retrieval
    # facets must never become evaluation constraints.
    retrieval_list_fields = {
        "place_type": parsed.place_types,
        "activity": parsed.activities,
        "travel_style": parsed.travel_styles,
        "suitable_for": parsed.suitable_for,
    }
    for item in parsed.explicit_constraints:
        if item.key in retrieval_list_fields:
            values = retrieval_list_fields[item.key]
            if item.value not in values:
                values.append(item.value)
        elif item.key == "country":
            parsed.location.country = item.value
        elif item.key == "province":
            parsed.location.province = item.value
        elif item.key == "region":
            parsed.location.region = item.value
        elif item.key == "budget":
            parsed.constraints.budget = item.value
        elif item.key == "duration_days":
            try:
                parsed.constraints.duration_days = int(item.value)
            except ValueError:
                pass
        elif item.key == "max_distance_km":
            try:
                parsed.constraints.max_distance_km = float(item.value)
            except ValueError:
                pass
        elif item.key in {"date_from", "date_to", "near_place"}:
            setattr(parsed.constraints, item.key, item.value)

    if parsed.intent not in ALLOWED_QUERY_INTENTS:
        print(
            "[QUERY PARSER WARNING] "
            f"Invalid intent returned: {parsed.intent}"
        )
        parsed.intent_was_invalid = True
        parsed.intent = "travel_information"

    if parsed.operation not in ALLOWED_QUERY_OPERATIONS:
        print(
            "[QUERY PARSER WARNING] "
            f"Invalid operation returned: {parsed.operation}"
        )
        parsed.operation_was_invalid = True
        parsed.operation = "lookup"

    if (
        parsed.constraints.budget is not None
        and parsed.constraints.budget not in ALLOWED_BUDGET_LEVELS
    ):
        print(
            "[QUERY PARSER WARNING] "
            f"Invalid budget returned: {parsed.constraints.budget}"
        )
        parsed.constraints.budget = None

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
            intent="travel_information",
            operation="lookup",
            raw_intent=None,
            raw_operation=None,
            parser_used_fallback=True,
        )
