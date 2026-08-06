import json
import re
import ollama

from ingestion.normalize_data import normalize_metadata
from schemas.metadata_schema import TourismMetadata
from config.prompts import build_metadata_prompt
from test import EXTRACTION_SCHEMA


def extract_json_from_text(text: str) -> dict:
    """
    Safely parse JSON from Ollama output.

    Sometimes small models still return extra text.
    This function tries normal json.loads first,
    then extracts the first {...} block.
    """

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)

    if not match:
        raise ValueError(f"No JSON object found in model output: {text[:500]}")

    return json.loads(match.group(0))


def extract_ollama_metadata(
    chunk_text: str,
    context_text: str = "",
    model: str = "qwen3:8b",
) -> TourismMetadata:
    try:
        prompt = build_metadata_prompt(chunk_text,
                                       context_text=context_text,)

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
                        "Do not put long sentences inside arrays."
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

        metadata = normalize_metadata(metadata)

        return metadata

    except Exception as e:
        print("[AI METADATA FAILED]")
        print(f"Model: {model}")
        print(f"Error: {e}")
        print("Chunk preview:")
        print(chunk_text[:500])

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
            reasoning=f"AI metadata extraction failed: {e}",
        )
# import json
# import ollama

# from config.prompts import METADATA_PROMPT, build_metadata_prompt
# from config.vocab import (
#     ALLOWED_CHUNK_TOPICS,
#     ALLOWED_PLACE_TYPES,
#     ALLOWED_TRAVEL_STYLES,
# )

# from ingestion.normalize_data import (
#     normalize_metadata,
# )

# from schemas.metadata_schema import (
#     TourismMetadata,
# )


# EXTRACTION_SCHEMA = {
#     "type": "object",

#     "properties": {

#         "country": {
#             "type": ["string", "null"]
#         },

#         "city": {
#             "type": ["string", "null"]
#         },

#         "province": {
#             "type": ["string", "null"]
#         },

#         "place_name": {
#             "type": ["string", "null"]
#         },

#         "place_type": {
#             "type": ["string", "null"]
#         },

#         "ai_tags": {
#             "type": "array",
#             "items": {"type": "string"},
#         },

#         "ai_activities": {
#             "type": "array",
#             "items": {"type": "string"},
#         },

#         "ai_travel_styles": {
#             "type": "array",
#             "items": {"type": "string"},
#         },

#         "ai_suitable_for": {
#             "type": "array",
#             "items": {"type": "string"},
#         },

#         "chunk_topic": {
#             "type": ["string", "null"]
#         },

#         "summary": {
#             "type": ["string", "null"]
#         },

#         "confidence": {
#             "type": "number"
#         },

#         "reasoning": {
#             "type": ["string", "null"]
#         },
#     },

#     "required": [
#         "country",
#         "city",
#         "province",
#         "place_name",
#         "place_type",
#         "ai_tags",
#         "ai_activities",
#         "ai_travel_styles",
#         "ai_suitable_for",
#         "chunk_topic",
#         "summary",
#         "confidence",
#         "reasoning",
#     ],
# }


# def extract_ollama_metadata(
#     chunk_text: str,
#     model: str = "phi3:mini",
# ) -> TourismMetadata:

#     prompt = build_metadata_prompt(chunk_text)

#     response = ollama.chat(
#         model=model,
#         messages=[
#             {
#                 "role": "system",
#                 "content": (
#                     "You only output valid JSON."
#                 ),
#             },
#             {
#                 "role": "user",
#                 "content": prompt,
#             },
#         ],

#         format=EXTRACTION_SCHEMA,

#         options={
#             "temperature": 0,
#         },
#     )

#     content = (
#         response["message"]["content"]
#         .strip()
#     )

#     ai_json = json.loads(content)

#     metadata = TourismMetadata(
#         **ai_json
#     )

#     metadata = normalize_metadata(
#         metadata
#     )

#     return metadata
# # import json
# # import os
# # import ollama
# # from dotenv import load_dotenv
# # from openai import OpenAI

# # from config.prompts import METADATA_PROMPT

# # from schemas.metadata_schema import (
# #     TourismMetadata,
# # )

# # load_dotenv()

# # client = OpenAI(
# #     api_key=os.getenv("OPENAI_API_KEY")
# # )


# # def extract_ai_metadata(chunk_text):

# #     # use simple replace to avoid str.format parsing of braces inside the prompt
# #     prompt = METADATA_PROMPT.replace("{chunk_text}", chunk_text)

# #     response = client.chat.completions.create(
# #         model="gpt-4o-mini",
# #         messages=[
# #             {
# #                 "role": "system",
# #                 "content": (
# #                     "You are a tourism metadata extraction system."
# #                 ),
# #             },
# #             {
# #                 "role": "user",
# #                 "content": prompt,
# #             },
# #         ],
# #         temperature=0,
# #         response_format={
# #             "type": "json_object"
# #         },
# #     )

# #     content = response.choices[0].message.content

# #     ai_json = json.loads(content)

# #     validated = TourismMetadata(
# #         **ai_json
# #     )

# #     return validated

# # def extract_ollama_metadata(chunk_text):

# #     # use simple replace to avoid str.format parsing of braces inside the prompt
# #     prompt = METADATA_PROMPT.replace("{chunk_text}", chunk_text)

# #     response = ollama.chat(

# #         model="llama3",

# #         messages=[
# #             {
# #                 "role": "system",
# #                 "content": (
# #                     "You are a tourism metadata extraction system. "
# #                     "Return ONLY valid JSON."
# #                 ),
# #             },
# #             {
# #                 "role": "user",
# #                 "content": prompt,
# #             },
# #         ],

# #         options={
# #             "temperature": 0,
# #         },
# #     )

# #     content = response["message"]["content"]

# #     # remove markdown code block if exists
# #     content = content.strip()

# #     if content.startswith("```json"):
# #         content = content.replace(
# #             "```json",
# #             ""
# #         )

# #     if content.endswith("```"):
# #         content = content[:-3]

# #     content = content.strip()

# #     ai_json = json.loads(content)

# #     validated = TourismMetadata(
# #         **ai_json
# #     )

# #     return validated

# # import json
# # import traceback
# # import ollama

# # from config.vocab import ALLOWED_CHUNK_TOPICS, ALLOWED_PLACE_TYPES, ALLOWED_TRAVEL_STYLES
# # from ingestion.normalize_data import normalize_metadata
# # from schemas.metadata_schema import TourismMetadata
# # from config.prompts import METADATA_PROMPT

# # EXTRACTION_SCHEMA = {
# #     "type": "object",
# #     "properties": {
# #         "country": {"type": ["string", "null"]},
# #         "city": {"type": ["string", "null"]},
# #         "province": {"type": ["string", "null"]},
# #         "place_name": {"type": ["string", "null"]},
# #         "place_type": {"type": ["string", "null"]},

# #         "ai_tags": {
# #             "type": "array",
# #             "items": {"type": "string"},
# #         },

# #         "ai_activities": {
# #             "type": "array",
# #             "items": {"type": "string"},
# #         },

# #         "ai_travel_styles": {
# #             "type": "array",
# #             "items": {"type": "string"},
# #         },

# #         "ai_suitable_for": {
# #             "type": "array",
# #             "items": {"type": "string"},
# #         },

# #         "chunk_topic": {
# #             "type": ["string", "null"]
# #         },

# #         "summary": {
# #             "type": ["string", "null"]
# #         },

# #         "confidence": {
# #             "type": "number"
# #         },

# #         "reasoning": {
# #             "type": ["string", "null"]
# #         },
# #     },

# #     "required": [
# #         "country",
# #         "city",
# #         "province",
# #         "place_name",
# #         "place_type",
# #         "ai_tags",
# #         "ai_activities",
# #         "ai_travel_styles",
# #         "ai_suitable_for",
# #         "chunk_topic",
# #         "summary",
# #         "confidence",
# #         "reasoning",
# #     ],
# # }

# # def get_pydantic_schema(model_class):
# #     """
# #     Support both Pydantic v2 and v1.
# #     """
# #     if hasattr(model_class, "model_json_schema"):
# #         return model_class.model_json_schema()

# #     return model_class.schema()


# # schema = get_pydantic_schema(TourismMetadata)

# # chunk_text = """
# # Hoan Kiem Lake is a historical attraction in Hanoi suitable for photography and families.
# # """

# # formatted_prompt = METADATA_PROMPT.format(

# #     place_types=ALLOWED_PLACE_TYPES,

# #     chunk_topics=ALLOWED_CHUNK_TOPICS,

# #     travel_styles=ALLOWED_TRAVEL_STYLES,

# #     chunk_text=chunk_text,
# # )
# # response = ollama.chat(

# #     model="phi3:mini",

# #     messages=[
# #         {
# #             "role": "system",
# #             "content": (
# #                 "You only output valid JSON."
# #             ),
# #         },
# #         {
# #             "role": "user",
# #             "content": formatted_prompt,
# #         },
# #     ],

# #     format=EXTRACTION_SCHEMA,

# #     options={
# #         "temperature": 0,
# #     },
# # )
# # content = response["message"]["content"].strip()

# # print("RAW RESPONSE:")
# # print(content)

# # try:
# #     ai_json = json.loads(content)
# # except json.JSONDecodeError:
# #     print("Failed to parse JSON. Raw content:")
# #     print(repr(content))
# #     print(traceback.format_exc())
# #     raise

# # print("\nPARSED JSON:")
# # print(ai_json)

# # metadata = TourismMetadata(**ai_json)
# # metadata = normalize_metadata(
# #     metadata
# # )

# # print("\nVALIDATED OBJECT:")
# # print(metadata)