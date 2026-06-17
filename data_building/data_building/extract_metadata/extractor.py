import json
import os
from typing import Optional
from data_building.extract_metadata.extract_config.schema import GEMINI_EXTRACTION_SCHEMA
from .helpers import fallback_metadata, safe_normalize_metadata
import ollama
from openai import OpenAI
from google import genai
from google.genai import types
from dotenv import load_dotenv
from schemas.metadata_schema import TourismMetadata
from .extract_config import EXTRACTION_SCHEMA, build_metadata_prompt

load_dotenv()

# =========================================================
# CONFIG
# =========================================================

METADATA_PROVIDER = os.getenv(
    "METADATA_PROVIDER",
    "gemini",
).lower()

OPENAI_METADATA_MODEL = os.getenv(
    "OPENAI_METADATA_MODEL",
    "gpt-4.1-mini",
)

OLLAMA_METADATA_MODEL = os.getenv(
    "OLLAMA_METADATA_MODEL",
    "qwen3:8b",
)

GEMINI_METADATA_MODEL = os.getenv(
    "GEMINI_METADATA_MODEL",
    "gemini-3.5-flash",
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# openai_client = OpenAI(
#     api_key=os.getenv("OPENAI_API_KEY"),
# )


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
# Gemini
# =========================================================

gemini_client = None


def get_gemini_client():
    global gemini_client

    if gemini_client is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is missing")

        gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    return gemini_client

def extract_gemini_metadata(
    chunk_text: str,
    context_text: str = "",
    model: str = GEMINI_METADATA_MODEL,
) -> TourismMetadata:
    """
    Extract tourism metadata using Gemini API.

    Useful as a free/cloud alternative to OpenAI.
    """

    prompt = build_metadata_prompt(
        chunk_text=chunk_text,
        context_text=context_text,
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=(
                            "You are a strict tourism metadata extraction system.\n"
                            "Return only structured JSON matching the schema.\n"
                            "Use only allowed labels from the prompt.\n"
                            "Do not put long sentences inside arrays.\n"
                            "The current chunk is the main source of truth.\n"
                            "Context is only for resolving ambiguous location or topic.\n"
                            "Do not copy city/place from context if the current chunk says something different.\n\n"
                            f"{prompt}"
                        )
                    )
                ],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0,

            response_mime_type="application/json",
            response_schema=GEMINI_EXTRACTION_SCHEMA,
        ),
    )

    if not response.text:
        raise ValueError("Gemini returned empty response")

    raw_text = response.text
    # data = json.loads(raw_text)
    ai_json = json.loads(response.text)

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
    - "gemini"

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

    if selected_provider == "gemini":
        return extract_gemini_metadata(
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
