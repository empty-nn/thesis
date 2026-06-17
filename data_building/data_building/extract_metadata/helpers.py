# ingestion/extract_metadata.py

import json
import re
from ingestion.normalize_data import normalize_metadata
from schemas.metadata_schema import TourismMetadata


# =========================================================
# HELPERS
# =========================================================

def extract_json_from_text(text: str) -> dict:
    """
    Useful for local/Ollama models that sometimes return extra text.
    OpenAI structured output usually does not need this.
    """

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)

    if not match:
        raise ValueError(
            f"No JSON object found in model output: {text[:500]}"
        )

    return json.loads(match.group(0))


def fallback_metadata(
    chunk_text: str,
    reason: str,
) -> TourismMetadata:
    """
    Fallback metadata when AI extraction fails.
    Keeps pipeline running.
    """

    return TourismMetadata(
        country="Vietnam",
        city=None,
        province=None,
        place_name=None,
        place_type=None,
        ai_tags=[],
        ai_activities=[],
        ai_travel_styles=[],
        ai_suitable_for=[],
        chunk_topic=None,
        summary=chunk_text[:300],
        confidence=0.0,
        reasoning=reason,
    )


def safe_normalize_metadata(
    metadata: TourismMetadata,
) -> TourismMetadata:
    """
    Normalize metadata but do not crash if normalization has issues.
    """

    try:
        return normalize_metadata(metadata)
    except Exception as e:
        print("[NORMALIZE METADATA FAILED]")
        print(e)
        return metadata

