# ingestion/extract_metadata.py

import json
import os
import re
from typing import Optional

import ollama
from openai import OpenAI
from dotenv import load_dotenv

from config.prompts import build_metadata_prompt
from ingestion.normalize_data import normalize_metadata
from schemas.metadata_schema import TourismMetadata
from test import EXTRACTION_SCHEMA

load_dotenv()

# =========================================================
# CONFIG
# =========================================================

METADATA_PROVIDER = os.getenv(
    "METADATA_PROVIDER",
    "openai",
).lower()

OPENAI_METADATA_MODEL = os.getenv(
    "OPENAI_METADATA_MODEL",
    "gpt-4.1-mini",
)

OLLAMA_METADATA_MODEL = os.getenv(
    "OLLAMA_METADATA_MODEL",
    "qwen3:8b",
)

openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)
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


# =========================================================
# OPENAI EXTRACTION
# =========================================================

def extract_openai_metadata(
    chunk_text: str,
    context_text: str = "",
    model: str = OPENAI_METADATA_MODEL,
) -> TourismMetadata:
    """
    Extract tourism metadata using OpenAI Responses API.

    Recommended for final/high-quality ingestion.
    """

    prompt = build_metadata_prompt(
        chunk_text=chunk_text,
        context_text=context_text,
    )

    response = openai_client.responses.parse(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a strict tourism metadata extraction system. "
                    "Return only structured data matching the schema. "
                    "Use only allowed labels from the prompt. "
                    "Do not put long sentences inside arrays. "
                    "The current chunk is the main source of truth. "
                    "Context is only for resolving ambiguous location or topic. "
                    "Do not copy city/place from context if the current chunk says something different."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        text_format=TourismMetadata,
        temperature=0,
        max_output_tokens=700,
    )

    metadata = response.output_parsed

    metadata = safe_normalize_metadata(metadata)

    return metadata


# =========================================================
# OLLAMA EXTRACTION
# =========================================================

def extract_ollama_metadata(
    chunk_text: str,
    context_text: str = "",
    model: str = OLLAMA_METADATA_MODEL,
) -> TourismMetadata:
    """
    Extract tourism metadata using local Ollama.

    Useful for cheap local testing.
    OpenAI is usually better for final metadata quality.
    """

    prompt = build_metadata_prompt(
        chunk_text=chunk_text,
        context_text=context_text,
    )

    response = ollama.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "/no_think\n"
                    "You are a strict tourism metadata extraction system. "
                    "Return ONLY valid JSON. "
                    "Do not use Markdown. "
                    "Do not explain. "
                    "Use only allowed labels from the prompt. "
                    "Do not put long sentences inside arrays. "
                    "The current chunk is the main source of truth. "
                    "Do not copy city/place from context if the current chunk says something different."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        format=EXTRACTION_SCHEMA,
        think=False,
        stream=False,
        options={
            "temperature": 0,
            "num_predict": 700,
            "num_ctx": 4096,
        },
    )

    content = response["message"].get("content", "").strip()

    if not content:
        thinking = response["message"].get("thinking", "")
        raise ValueError(
            "Model returned empty content. "
            f"Thinking preview: {thinking[:500]}"
        )

    ai_json = extract_json_from_text(content)

    metadata = TourismMetadata(**ai_json)

    metadata = safe_normalize_metadata(metadata)

    return metadata


# =========================================================
# MAIN ROUTER
# =========================================================

def extract_metadata(
    chunk_text: str,
    context_text: str = "",
    provider: Optional[str] = None,
) -> TourismMetadata:
    """
    Main metadata extraction router.

    provider:
    - "openai"
    - "ollama"

    Default comes from:
    METADATA_PROVIDER=openai
    """

    selected_provider = (
        provider or METADATA_PROVIDER
    ).lower()

    if selected_provider == "openai":
        return extract_openai_metadata(
            chunk_text=chunk_text,
            context_text=context_text,
        )

    if selected_provider == "ollama":
        return extract_ollama_metadata(
            chunk_text=chunk_text,
            context_text=context_text,
        )

    raise ValueError(
        f"Unsupported metadata provider: {selected_provider}"
    )


def safe_extract_ai_metadata(
    chunk_text: str,
    context_text: str = "",
    provider: Optional[str] = None,
) -> TourismMetadata:
    """
    Safe wrapper for pipeline use.
    If extraction fails, return fallback metadata instead of stopping ingestion.
    """

    selected_provider = (
        provider or METADATA_PROVIDER
    ).lower()

    try:
        return extract_metadata(
            chunk_text=chunk_text,
            context_text=context_text,
            provider=selected_provider,
        )

    except Exception as e:
        print("[AI METADATA FAILED]")
        print(f"Provider: {selected_provider}")
        print(f"OpenAI model: {OPENAI_METADATA_MODEL}")
        print(f"Ollama model: {OLLAMA_METADATA_MODEL}")
        print(f"Error: {e}")
        print("Chunk preview:")
        print(chunk_text[:500])

        return fallback_metadata(
            chunk_text=chunk_text,
            reason=f"AI metadata extraction failed: {e}",
        )


# =========================================================
# BACKWARD COMPATIBILITY
# =========================================================

def extract_ollama_metadata_legacy(
    chunk_text: str,
    model: str = OLLAMA_METADATA_MODEL,
) -> TourismMetadata:
    """
    Optional old-style function if some old code calls only chunk_text + model.
    """

    return extract_ollama_metadata(
        chunk_text=chunk_text,
        context_text="",
        model=model,
    )