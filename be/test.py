import json
import traceback
import ollama

from config.vocab import ALLOWED_CHUNK_TOPICS, ALLOWED_PLACE_TYPES, ALLOWED_TRAVEL_STYLES
from ingestion.normalize_data import normalize_metadata
from schemas.metadata_schema import TourismMetadata
from config.prompts import METADATA_PROMPT

from config.vocab import (
    ALLOWED_PLACE_TYPES,
    ALLOWED_CHUNK_TOPICS,
    ALLOWED_TRAVEL_STYLES,
    ALLOWED_SUITABLE_FOR,
)


EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "country": {
            "type": ["string", "null"],
            "description": "Country name, for example Vietnam.",
        },

        "city": {
            "type": ["string", "null"],
            "description": "City name if clearly mentioned, for example Hanoi, Da Nang, Ho Chi Minh City.",
        },

        "province": {
            "type": ["string", "null"],
            "description": "Province or region if clearly mentioned.",
        },

        "place_name": {
            "type": ["string", "null"],
            "description": "Main place, destination, attraction, or location discussed in the chunk.",
        },

        "place_type": {
            "type": ["string", "null"],
            "enum": ALLOWED_PLACE_TYPES + [None],
            "description": "Must be one of the allowed place types.",
        },

        "ai_tags": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "string",
                "maxLength": 40,
                "description": "Short lowercase tourism tag. Do not use full sentences.",
            },
        },

        "ai_activities": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "string",
                "maxLength": 40,
                "description": "Short activity label, for example sightseeing, hiking, food_tour.",
            },
        },

        "ai_travel_styles": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "string",
                "enum": ALLOWED_TRAVEL_STYLES,
                "description": "Must be one of the allowed travel styles.",
            },
        },

        "ai_suitable_for": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "string",
                "enum": ALLOWED_SUITABLE_FOR,
                "description": "Must be one of the allowed suitable-for labels.",
            },
        },

        "chunk_topic": {
            "type": ["string", "null"],
            "enum": ALLOWED_CHUNK_TOPICS + [None],
            "description": "Main topic of the chunk.",
        },

        "summary": {
            "type": ["string", "null"],
            "maxLength": 300,
            "description": "One concise tourism summary sentence.",
        },

        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },

        "reasoning": {
            "type": ["string", "null"],
            "maxLength": 250,
            "description": "One short sentence explaining the selected metadata. No long reasoning.",
        },
    },

    "required": [
        "country",
        "city",
        "province",
        "place_name",
        "place_type",
        "ai_tags",
        "ai_activities",
        "ai_travel_styles",
        "ai_suitable_for",
        "chunk_topic",
        "summary",
        "confidence",
        "reasoning",
    ],
}

