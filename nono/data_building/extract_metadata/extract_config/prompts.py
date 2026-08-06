from config.vocab import (
    ALLOWED_PLACE_TYPES,
    ALLOWED_CHUNK_TOPICS,
    ALLOWED_TRAVEL_STYLES,
    ALLOWED_SUITABLE_FOR,
)
import json
from typing import Any, Dict, List


METADATA_PROMPT = """
You are an information extraction system for a tourism RAG database.

Extract structured tourism metadata from the provided chunk.
Return a concise 1-sentence tourism summary.

IMPORTANT OUTPUT RULES:
- Return ONLY valid JSON.
- Do not include Markdown.
- Do not include explanations outside JSON.
- Do not invent information that is not present or strongly implied.
- Use null if unknown.
- Use [] if no suitable values exist.
- Use lowercase snake_case labels in arrays.
- Do not return full sentences inside arrays.
- Array values must be short labels only.
- Maximum 8 ai_tags.
- Maximum 8 ai_activities.
- Maximum 4 ai_travel_styles.
- Maximum 4 ai_suitable_for.

Allowed place_type:
{place_types}

Allowed chunk_topic:
{chunk_topics}

Allowed ai_travel_styles:
{travel_styles}

Allowed ai_suitable_for:
{suitable_for}

FIELD RULES:

country:
- Use the country name if explicitly mentioned or clearly implied by the document context.
- For this dataset, if the chunk is clearly about Vietnam tourism, country can be "Vietnam".

city:
- Use city name only if the chunk is about a specific city.
- Examples: "Hanoi", "Da Nang", "Ho Chi Minh City", "Hoi An".

province:
- Use province/region only if clearly mentioned.
- If unknown, use null.

place_name:
- Use the main place, attraction, destination, or location discussed in the chunk.
- If the chunk is a general country/city overview, place_name may be the country or city.
- If no clear place exists, use null.

place_type:
- Must be one value from Allowed place_type.
- Use "general" for broad overview chunks.
- Use "city" for city overview chunks.
- Use "attraction" for specific tourist attractions.

ai_tags:
- Short descriptive labels.
- Examples: "street_food", "pagoda", "beach", "heritage", "night_market".
- Do not use long phrases.

ai_activities:
- Short activity labels.
- Examples: "sightseeing", "hiking", "swimming", "shopping", "food_tour", "museum_visit".
- Do not use long phrases.

ai_travel_styles:
- Must choose only from Allowed ai_travel_styles.
- Do not create new labels.

ai_suitable_for:
- Must choose only from Allowed ai_suitable_for.
- Do not create new labels.
- Do not return long sentences.

chunk_topic:
- Must be one value from Allowed chunk_topic.
- Use "overview" for destination introductions.
- Use "travel_tips" for advice.
- Use "transportation" for transport information.
- Use "food" for cuisine and restaurant content.
- Use "attraction" for specific places to visit.

summary:
- One concise sentence.
- Describe what the chunk says.
- Do not add unsupported facts.

confidence:
- Use a number from 0.0 to 1.0.

reasoning:
- One short sentence explaining why the main metadata was selected.
- Do not include chain-of-thought.
- Do not include long reasoning.

JSON schema:
{{
    "country": null,
    "city": null,
    "province": null,
    "place_name": null,
    "place_type": null,
    "ai_tags": [],
    "ai_activities": [],
    "ai_travel_styles": [],
    "ai_suitable_for": [],
    "chunk_topic": null,
    "summary": null,
    "confidence": 0.0,
    "reasoning": null
}}

Context:
\"\"\"
{context_text}
\"\"\"

Important:
- Context is only supporting information.
- The current chunk is the main source of truth.
- Do not extract specific attractions, activities, or tags from context unless the current chunk also supports them.

Chunk:
\"\"\"
{chunk_text}
\"\"\"
"""


def build_metadata_prompt(
    chunk_text: str,
    context_text: str = "",
) -> str:
    return METADATA_PROMPT.format(
        place_types=", ".join(ALLOWED_PLACE_TYPES),
        chunk_topics=", ".join(ALLOWED_CHUNK_TOPICS),
        travel_styles=", ".join(ALLOWED_TRAVEL_STYLES),
        suitable_for=", ".join(ALLOWED_SUITABLE_FOR),
        context_text=context_text,
        chunk_text=chunk_text,
    )

BATCH_METADATA_PROMPT = """
You are an information extraction system for a tourism RAG database.

Extract structured tourism metadata from multiple document chunks.
Each chunk must be processed separately.

IMPORTANT OUTPUT RULES:
- Return ONLY valid JSON.
- Do not include Markdown.
- Do not include explanations outside JSON.
- Do not invent information that is not present or strongly implied.
- Use null if unknown.
- Use [] if no suitable values exist.
- Use lowercase snake_case labels in arrays.
- Do not return full sentences inside arrays.
- Array values must be short labels only.
- Maximum 8 ai_tags.
- Maximum 8 ai_activities.
- Maximum 4 ai_travel_styles.
- Maximum 4 ai_suitable_for.
- Return exactly one item for every input chunk.
- Keep the original chunk_index for each item.
- Do not merge chunks together.
- Do not mix metadata between chunks.

Allowed place_type:
{place_types}

Allowed chunk_topic:
{chunk_topics}

Allowed ai_travel_styles:
{travel_styles}

Allowed ai_suitable_for:
{suitable_for}

FIELD RULES:

country:
- Use the country name if explicitly mentioned or clearly implied by the document context.
- For this dataset, if the chunk is clearly about Vietnam tourism, country can be "Vietnam".

city:
- Use city name only if the chunk is about a specific city.
- Examples: "Hanoi", "Da Nang", "Ho Chi Minh City", "Hoi An".
- If a heading clearly gives the city, you may infer city from the heading.

province:
- Use province/region only if clearly mentioned.
- If unknown, use null.

place_name:
- Use the main place, attraction, destination, or location discussed in the chunk.
- If the chunk is a general country/city overview, place_name may be the country or city.
- If no clear place exists, use null.

place_type:
- Must be one value from Allowed place_type.
- Use "general" only if it exists in Allowed place_type.
- Use "city" only if it exists in Allowed place_type.
- Use "attraction" only if it exists in Allowed place_type.
- If no allowed value fits, use null.

ai_tags:
- Short descriptive labels.
- Examples: "street_food", "pagoda", "beach", "heritage", "night_market".
- Do not use long phrases.

ai_activities:
- Short activity labels.
- Examples: "sightseeing", "hiking", "swimming", "shopping", "food_tour", "museum_visit".
- Do not use long phrases.

ai_travel_styles:
- Must choose only from Allowed ai_travel_styles.
- Do not create new labels.

ai_suitable_for:
- Must choose only from Allowed ai_suitable_for.
- Do not create new labels.
- Do not return long sentences.

chunk_topic:
- Must be one value from Allowed chunk_topic.
- Use only labels that exist in Allowed chunk_topic.
- If no allowed value fits, use null.

summary:
- One concise sentence.
- Describe what the chunk says.
- Do not add unsupported facts.

confidence:
- Use a number from 0.0 to 1.0.

reasoning:
- One short sentence explaining why the main metadata was selected.
- Do not include chain-of-thought.
- Do not include long reasoning.

Required JSON output shape:

{{
  "items": [
    {{
      "chunk_index": 0,
      "country": null,
      "city": null,
      "province": null,
      "place_name": null,
      "place_type": null,
      "ai_tags": [],
      "ai_activities": [],
      "ai_travel_styles": [],
      "ai_suitable_for": [],
      "chunk_topic": null,
      "summary": null,
      "confidence": 0.0,
      "reasoning": null
    }}
  ]
}}

Document context:
\"\"\"
{context_text}
\"\"\"

Important:
- Context is only supporting information.
- The current chunk is the main source of truth.
- Do not extract specific attractions, activities, or tags from context unless the current chunk also supports them.
- Previous country/city can help only when the current chunk clearly continues the same section.

Input chunks:
{chunks_json}
"""


def truncate_text(text: str, max_chars: int = 3000) -> str:
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n...[TRUNCATED]"


def build_batch_metadata_prompt(
    batch_chunks: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> str:
    chunk_payload = []

    for chunk in batch_chunks:
        chunk_payload.append(
            {
                "chunk_index": chunk["chunk_index"],
                "section_heading": chunk.get("section_heading"),
                "header_metadata": chunk.get("header_metadata", {}),
                "chunk_text": truncate_text(
                    chunk.get("chunk_text", ""),
                    max_chars=3000,
                ),
            }
        )

    context_text = f"""
        Document title: {context.get("document_title")}
        Source file: {context.get("source_file")}

        Previous chunk summary: {context.get("previous_summary")}
        Previous heading: {context.get("previous_heading")}
        Previous country: {context.get("previous_country")}
        Previous city: {context.get("previous_city")}
        """.strip()

    return BATCH_METADATA_PROMPT.format(
        place_types=", ".join(ALLOWED_PLACE_TYPES),
        chunk_topics=", ".join(ALLOWED_CHUNK_TOPICS),
        travel_styles=", ".join(ALLOWED_TRAVEL_STYLES),
        suitable_for=", ".join(ALLOWED_SUITABLE_FOR),
        context_text=context_text,
        chunks_json=json.dumps(
            chunk_payload,
            ensure_ascii=False,
            indent=2,
        ),
    )

CLEAN_BATCH_PROMPT = """
You are an information extraction system for a tourism RAG database.

Extract structured metadata for every chunk in the list below.
Each chunk must be processed independently; do not merge information across chunks.

Allowed place_type: {place_types}
Allowed chunk_topic: {chunk_topics}
Allowed ai_travel_styles: {travel_styles}
Allowed ai_suitable_for: {suitable_for}

FIELD RULES:
- country: Use the country name if explicitly mentioned or clearly implied. For this dataset, default to "Vietnam" when appropriate.
- city/province: Use only if specific; otherwise null.
- place_name: Main attraction, place, or location the chunk focuses on.
- place_type: Exactly one from Allowed place_type, or null.
- ai_tags: Short labels (e.g., "street_food", "pagoda"). Max 8.
- ai_activities: Short action labels (e.g., "hiking", "sightseeing"). Max 8.
- ai_travel_styles: Only from Allowed. Max 4.
- ai_suitable_for: Only from Allowed. Max 4.
- chunk_topic: Exactly one from Allowed chunk_topic, or null.
- summary: One concise sentence describing the chunk.
- confidence: 0.0 (low) to 1.0 (high).
- reasoning: (optional) One short sentence about the main decision.

Do not invent information. Use null or [] when no suitable value exists.
Array values must be short labels, not full sentences.

Use section_heading and header_metadata to disambiguate location, but the chunk text is the primary source of truth.
Context is supporting only: do not copy city/place from context unless the current chunk confirms it.

Document context:
\"\"\"
{context_text}
\"\"\"

Input chunks:
{chunks_json}
"""

def truncate_text_v2(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    # Find the last sentence-ending punctuation within max_chars
    truncated = text[:max_chars]
    # Look for . ! ? followed by space or end
    last_sentence_end = max(
        truncated.rfind(". "),
        truncated.rfind("? "),
        truncated.rfind("! "),
        truncated.rfind(".\n"),
    )
    if last_sentence_end > 0 and last_sentence_end > max_chars * 0.5:
        truncated = truncated[:last_sentence_end+1]  # include the punctuation
    return truncated + "\n...[TRUNCATED]"

def build_batch_metadata_prompt_deepseek(
    batch_chunks: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> str:
    chunk_payload = []
    for chunk in batch_chunks:
        chunk_payload.append(
            {
                "chunk_index": chunk["chunk_index"],
                "section_heading": chunk.get("section_heading"),
                "header_metadata": chunk.get("header_metadata", {}),
                "chunk_text": truncate_text_v2(chunk.get("chunk_text", ""), max_chars=3000),
            }
        )

    # Build a concise context string
    context_lines = []
    if context.get("document_title"):
        context_lines.append(f"Document title: {context['document_title']}")
    if context.get("source_file"):
        context_lines.append(f"Source file: {context['source_file']}")
    if context.get("previous_summary"):
        context_lines.append(f"Previous chunk summary: {context['previous_summary']}")
    if context.get("previous_heading"):
        context_lines.append(f"Previous heading: {context['previous_heading']}")
    if context.get("previous_country"):
        context_lines.append(f"Previous country: {context['previous_country']}")
    if context.get("previous_city"):
        context_lines.append(f"Previous city: {context['previous_city']}")

    context_text = "\n".join(context_lines) if context_lines else "No additional context."

    return CLEAN_BATCH_PROMPT.format(
        place_types=", ".join(ALLOWED_PLACE_TYPES),
        chunk_topics=", ".join(ALLOWED_CHUNK_TOPICS),
        travel_styles=", ".join(ALLOWED_TRAVEL_STYLES),
        suitable_for=", ".join(ALLOWED_SUITABLE_FOR),
        context_text=context_text,
        chunks_json=json.dumps(
            chunk_payload,
            ensure_ascii=False,
            indent=2,
        ),
    )