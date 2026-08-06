import json
import os
from typing import Optional
from data_building.extract_metadata.extract_config.prompts import build_batch_metadata_prompt_deepseek
from data_building.extract_metadata.extract_config.schema import GEMINI_EXTRACTION_SCHEMA, GEMINI_BATCH_EXTRACTION_SCHEMA
from .helpers import fallback_metadata, safe_normalize_metadata
import ollama
from openai import OpenAI
from google import genai
from google.genai import types
from dotenv import load_dotenv
from schemas.metadata_schema import TourismMetadata
from .extract_config import EXTRACTION_SCHEMA, build_metadata_prompt, build_batch_metadata_prompt
from typing import Optional, Dict, List, Any
from pydantic import AliasChoices, BaseModel, Field

def normalize_batch_response(
    ai_json: Any,
) -> Dict[str, Any]:
    """
    Normalize possible DeepSeek response shapes into:

    {
        "items": [...]
    }
    """
    # Model returned a raw list
    if isinstance(ai_json, list):
        return {"items": ai_json}

    if not isinstance(ai_json, dict):
        raise ValueError(
            "DeepSeek batch response must be a JSON object or array, "
            f"received {type(ai_json).__name__}"
        )

    # Correct response shape
    if isinstance(ai_json.get("items"), list):
        return ai_json

    # Common alternative keys
    for key in ("chunks", "results", "metadata"):
        if isinstance(ai_json.get(key), list):
            return {"items": ai_json[key]}

    # Model returned one item directly
    if "chunk_index" in ai_json:
        return {"items": [ai_json]}

    raise ValueError(
        'DeepSeek response does not contain an "items" array. '
        f"Received keys: {list(ai_json.keys())}"
    )

class BatchMetadataItem(TourismMetadata):
    chunk_index: int


class BatchMetadataResult(BaseModel):
     items: List[BatchMetadataItem] = Field(
        validation_alias=AliasChoices("items", "chunks")
    )

load_dotenv()

METADATA_PROVIDER = os.getenv("METADATA_PROVIDER", "deepseek").lower()
OPENAI_METADATA_MODEL = os.getenv("OPENAI_METADATA_MODEL", "gpt-4.1-mini")
OLLAMA_METADATA_MODEL = os.getenv("OLLAMA_METADATA_MODEL", "qwen3:8b")
GEMINI_METADATA_MODEL = os.getenv("GEMINI_METADATA_MODEL", "gemini-3.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_METADATA_MODEL = os.getenv("DEEPSEEK_METADATA_MODEL")
# openai_client = OpenAI(
#     api_key=os.getenv("OPENAI_API_KEY"),
# )

def extract_openai_metadata(
    chunk_text: str,
    context_text: str = "",
    model: str = OPENAI_METADATA_MODEL,
) -> TourismMetadata:
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
    )

    metadata = response.output_parsed

    metadata = safe_normalize_metadata(metadata)

    return metadata

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

gemini_client = None
deepseek_client = None

def get_gemini_client():
    global gemini_client

    if gemini_client is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is missing")

        gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    return gemini_client

def get_deepseek_client():
    global deepseek_client
    if deepseek_client is None:
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        if not deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is missing")
        deepseek_client = OpenAI(
            api_key=deepseek_api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    return deepseek_client

def extract_gemini_metadata(
    chunk_text: str,
    context_text: str = "",
    model: str = GEMINI_METADATA_MODEL,
) -> TourismMetadata:
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

def extract_metadata(
    chunk_text: str,
    context_text: str = "",
    provider: Optional[str] = None,
) -> TourismMetadata:
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
        print(f"Error: {e}")

        return fallback_metadata(
            chunk_text=chunk_text,
            reason=f"AI metadata extraction failed: {e}",
        )

def extract_gemini_metadata_batch(
    batch_chunks: List[Dict[str, Any]],
    context: Dict[str, Any],
    model: str = GEMINI_METADATA_MODEL,
) -> Dict[int, TourismMetadata]:
    """
    Extract tourism metadata for multiple chunks using one Gemini API call.

    Returns:
        {
            chunk_index: TourismMetadata(...)
        }
    """

    prompt = build_batch_metadata_prompt(
        batch_chunks=batch_chunks,
        context=context,
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
                            "Extract each chunk separately.\n"
                            "Keep original chunk_index.\n"
                            "Do not mix metadata between chunks.\n\n"
                            f"{prompt}"
                        )
                    )
                ],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=GEMINI_BATCH_EXTRACTION_SCHEMA,
        ),
    )
    print("Raw Gemini batch response:")
    print(response)
    if not response.text:
        raise ValueError("Gemini returned empty batch response")

    ai_json = json.loads(response.text)
    batch_result = BatchMetadataResult.model_validate(ai_json)

    input_indexes = {
        chunk["chunk_index"]
        for chunk in batch_chunks
    }

    metadata_by_index: Dict[int, TourismMetadata] = {}

    for item in batch_result.items:
        if item.chunk_index not in input_indexes:
            continue

        item_data = item.model_dump(
            exclude={"chunk_index"}
        )

        metadata = TourismMetadata(**item_data)
        metadata = safe_normalize_metadata(metadata)

        metadata_by_index[item.chunk_index] = metadata

    return metadata_by_index

DEEPSEEK_BATCH_SCHEMA = BatchMetadataResult.model_json_schema()

def extract_deepseek_metadata_batch(
    batch_chunks: List[Dict[str, Any]],
    context: Dict[str, Any],
    model: str = DEEPSEEK_METADATA_MODEL,
) -> Dict[int, TourismMetadata]:
    """
    Extract tourism metadata for multiple chunks using DeepSeek (OpenAI‑compatible).
    Returns {chunk_index: TourismMetadata}.
    """
    deepseek_client = get_deepseek_client()
    # Build the same prompt you use for Gemini batch extraction
    prompt = build_batch_metadata_prompt_deepseek(
        batch_chunks=batch_chunks,
        context=context,
    )

    system_msg = """
    You are a strict tourism metadata extraction system.

    Return only one valid JSON object.

    MANDATORY OUTPUT STRUCTURE:
    {
    "items": [
        {
        "chunk_index": 0
        }
    ]
    }

    Rules:
    - The top-level key must always be "items".
    - "items" must always be an array, even when there is only one chunk.
    - Return exactly one item for every input chunk.
    - Preserve every original chunk_index.
    - Never return a metadata item directly at the top level.
    - Never use "chunks", "results", or "metadata" as the top-level key.
    - Do not include Markdown or explanations.
    """.strip()

    response = deepseek_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=4096, 
        response_format={
            "type": "json_object",
            "json_schema": {
                "name": "batch_metadata",
                "strict": True,
                "schema": DEEPSEEK_BATCH_SCHEMA,
            },
        },
    )

    raw_text = response.choices[0].message.content
    if not raw_text:
        raise ValueError("DeepSeek returned empty batch response")

    ai_json = json.loads(raw_text)
    # ai_json = normalize_batch_response(ai_json)
    batch_result = BatchMetadataResult.model_validate(ai_json)

    input_indexes = {chunk["chunk_index"] for chunk in batch_chunks}
    metadata_by_index: Dict[int, TourismMetadata] = {}

    for item in batch_result.items:
        if item.chunk_index not in input_indexes:
            continue
        item_data = item.model_dump(exclude={"chunk_index"})
        metadata = TourismMetadata(**item_data)
        metadata = safe_normalize_metadata(metadata)
        metadata_by_index[item.chunk_index] = metadata

    return metadata_by_index

def extract_metadata_batch(
    batch_chunks: List[Dict[str, Any]],
    context: Dict[str, Any],
    provider: Optional[str] = None,
) -> Dict[int, TourismMetadata]:
    """
    Returns:
        {
            chunk_index: TourismMetadata(...)
        }
    """

    selected_provider = (provider or METADATA_PROVIDER).lower()

    if selected_provider == "gemini":
        return extract_gemini_metadata_batch(batch_chunks=batch_chunks, context=context)
    if selected_provider == "deepseek":
        return extract_deepseek_metadata_batch(batch_chunks=batch_chunks, context=context)
    
    raise ValueError(f"Unsupported batch metadata provider: {selected_provider}")

def safe_extract_ai_metadata_batch(
    batch_chunks: List[Dict[str, Any]],
    context: Dict[str, Any],
    provider: Optional[str] = None,
) -> Dict[int, TourismMetadata]:
    """
    Safe batch wrapper.
    If batch extraction fails, return fallback metadata for each chunk.
    """

    selected_provider = (
        provider or METADATA_PROVIDER
    ).lower()

    try:
        return extract_metadata_batch(
            batch_chunks=batch_chunks,
            context=context,
            provider=selected_provider,
        ) or {}

    except Exception as e:
        print("[AI METADATA BATCH FAILED]")
        print(f"Error: {e}")
    