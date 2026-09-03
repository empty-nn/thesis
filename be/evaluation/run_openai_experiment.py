from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import random
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Literal, TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, model_validator


BE_ROOT = Path(__file__).resolve().parents[1]
if str(BE_ROOT) not in sys.path:
    sys.path.insert(0, str(BE_ROOT))
load_dotenv(BE_ROOT / ".env")

from core.model_registry import (  # noqa: E402
    EMBEDDING_MODEL_NAME,
    RERANKER_MODEL_NAME,
    get_embedding_model,
    get_reranker,
    load_models,
    unload_models,
)
from config.vocab import (  # noqa: E402
    ALLOWED_ACTIVITIES,
    ALLOWED_BUDGET_LEVELS,
    ALLOWED_PLACE_TYPES,
    ALLOWED_REGIONS,
    ALLOWED_QUERY_INTENTS,
    ALLOWED_QUERY_OPERATIONS,
    ALLOWED_SUITABLE_FOR,
    ALLOWED_TRAVEL_STYLES,
)
from evaluation.run_thesis_evaluation import deterministic_metrics  # noqa: E402
from evaluation.thesis_evaluation_schema import (  # noqa: E402
    FinalAnswerScores,
    PreferenceConstraint,
    ThesisDataset,
    ThesisEvaluationCase,
)
from schemas.pipeline import UserTravelMemory  # noqa: E402
from data_building.extract_metadata.extractor import (  # noqa: E402
    DEEPSEEK_ANSWER_MODEL,
    DEEPSEEK_FAST_MODEL,
    DEEPSEEK_PARSER_MODEL,
    DEEPSEEK_RETRIEVAL_MODEL,
    DEEPSEEK_REASONING_MODEL,
)
from db.full_model import RagChunkORM  # noqa: E402
from db.session import SessionLocal  # noqa: E402
from services.answer_pipeline import build_evidence, generate_answer  # noqa: E402
from services.conversation_memory import ConversationState, derive_conversation_state  # noqa: E402
from services.external_web_fallback import generate_external_web_answer  # noqa: E402
from services.pipeline_runner import run_retrieval_pipeline  # noqa: E402
from services.query_processing import get_known_cities  # noqa: E402
from services.llm_telemetry import (  # noqa: E402
    activate_telemetry,
    deactivate_telemetry,
    estimate_cost_usd,
    normalize_usage,
    pricing_snapshot,
)


RETRIEVAL_FACET_KEYS = {"place_type", "activity", "travel_style", "suitable_for"}


def split_reference_constraints(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate hard request constraints from semantic retrieval facets."""
    constraints = [item for item in items if item.get("key") not in RETRIEVAL_FACET_KEYS]
    facets = [item for item in items if item.get("key") in RETRIEVAL_FACET_KEYS]
    return constraints, facets


def parsed_retrieval_facet_items(parsed) -> list[dict[str, str]]:
    groups = {
        "place_type": parsed.place_types,
        "activity": parsed.activities,
        "travel_style": parsed.travel_styles,
        "suitable_for": parsed.suitable_for,
    }
    return [
        {"key": key, "value": str(value)}
        for key, values in groups.items()
        for value in values
    ]


def parsed_hard_constraint_items(parsed) -> list[dict[str, str]]:
    items = query_constraint_items(parsed)
    return [item for item in items if item.get("key") not in RETRIEVAL_FACET_KEYS]


GENERATOR_SYSTEM = """
Create a synthetic but realistic conversational benchmark for a personalized Vietnam travel RAG system.
The output will be reviewed by a human. Do not claim that synthetic labels are human ground truth.

Return JSON with one key, `user`, containing:
- user_id and a distinct profile with expertise, answer_length, tone, explanation_style, interests,
  preferred_travel_styles, preferred_activities, budget_level, and avoid.
- memories: stable facts, each with a unique memory_id, key, and value.
- conversations: each with conversation_id and turns.
- every turn has turn_id, query, intent, operation, query_constraints, applicable_personalization,
  relevant_memory_ids, key_answer_facts, and difficulty (simple, contextual, or complex).
- turn_id must be an integer starting at 1, not a label such as TURN-01.
- query_constraints contains only facts explicitly stated or resolved from conversation context.
  Use key/value pairs and only these keys: country, region, city, province, place_type, activity,
  travel_style, suitable_for, budget, duration_days, date_from, date_to, near_place,
  max_distance_km. For list fields, emit one key/value pair per value.
- Do not convert interests or activities into suitable_for labels. Do not add broader related
  activities. Every query_constraint must be verifiable from the query or prior conversation.
- Geographic names use country/city/province; never duplicate them as place_type=country,
  place_type=city, place_type=province, or place_type=region.
- "solo" maps to suitable_for=solo_travelers, never to a travel_style. Prefer one direct label
  per phrase rather than encoding the same phrase as both activity and travel_style.
- For follow-up turns, include prior constraints only when needed to resolve the current query;
  do not copy the entire previous trip profile into every turn.
- Query-constraint values for place_type, activity, travel_style, suitable_for, and budget must
  come exactly from their supplied allowed lists.
- applicable_personalization contains only profile preferences or stable memories that should
  affect this turn's final answer, also represented as key/value pairs.
- relevant_memory_ids must contain every memory_id whose stable fact appears in
  applicable_personalization. Leave it empty only when no stored memory is relevant.

Requirements:
- Queries must concern travel in Vietnam and must be answerable from a Vietnam travel corpus.
- Use only cities from known_corpus_cities; do not generate a city absent from the corpus list.
- Within each conversation, later turns must naturally depend on earlier turns.
- Include factual, recommendation, itinerary, comparison, preference-dependent, ambiguous-follow-up,
  and multi-constraint queries.
- Do not include answers.
- Use exactly one intent from the supplied allowed_intents list. Never create a new intent label.
- Use exactly one operation from the supplied allowed_operations list. Intent is the travel
  task/domain and operation is how to handle it. A transport-mode comparison is
  intent=transport + operation=compare; a destination comparison is
  intent=recommendation + operation=compare.
- key_answer_facts should describe expected answer criteria, not invent precise changing facts such as prices.
- Keep stable preferences consistent throughout a user; temporary trip constraints belong in the query.
- Use only values from allowed_travel_styles for preferred_travel_styles, allowed_activities for
  preferred_activities, and allowed_budget_levels for budget_level. Do not paraphrase these values.
- Keep interests and avoid as arrays of concise natural-language strings. Put professional background and
  other stable biographical details in memories rather than embedding them in expertise.
- Use expertise as one of beginner, intermediate, experienced, expert; answer_length as concise,
  moderate, or detailed; tone as a short label; explanation_style as a short snake_case label.
Return JSON only.
""".strip()


RETRIEVAL_JUDGE_SYSTEM = """
You are creating blinded relevance labels for a Vietnam travel RAG evaluation.
Judge every supplied candidate independently of its rank or retrieval score.

Return JSON with:
- judgments: a list containing each supplied chunk_id and an integer relevance:
  0 = unrelated; 1 = related background but not directly useful; 2 = directly useful for one
  part of the request; 3 = directly and strongly useful for the main request or multiple parts.
Return every supplied chunk ID exactly once. Do not use rank, ordering, answer content, or retrieval
scores. Return JSON only.
""".strip()


ANSWER_JUDGE_SYSTEM = """
You are an independent evaluator of a personalized Vietnam travel RAG answer. Score each dimension
from 1 to 5 and give one short rationale per dimension.

Correctness uses the supplied expected answer criteria and evidence. Faithfulness requires externally
verifiable claims to be supported by supplied selected evidence. Personalization adherence checks
relevant profile preferences, stable memories, conversation context, and temporary constraints,
without rewarding the use of irrelevant profile data. Completeness checks all parts of the request.
When evidence is insufficient and the answer clearly says so, faithfulness and correctness may
remain high, but completeness should be lower. If the answer invents missing details, lower
faithfulness and correctness too; do not reward hallucinated coverage as completeness. Return JSON only.
The selected evidence is supplied in the exact reranked order used to generate the answer.
Resolve answer citations such as [E1] against the matching evidence_id field exactly.
""".strip()

EXTERNAL_ANSWER_JUDGE_SYSTEM = """
You are an independent evaluator of a personalized Vietnam travel answer that combines internal
RAG evidence with current external web evidence. Use web search to verify the answer's current
claims and supplied external source URLs or named real-time feeds before scoring.

Score correctness, faithfulness, personalization_adherence, and completeness from 1 to 5 and give
one short rationale per dimension. Treat expected_answer_criteria as coverage targets, not an
exclusive factual gold answer: do not penalize an independently verified current fact merely because
it is absent from those criteria. Faithfulness requires internal claims to match selected_evidence
and external claims to be supported by the supplied URLs, named live feeds, or your independent web
verification. Lower correctness and faithfulness for unsupported, stale, conflicting, or
misrepresented claims. Completeness checks all parts of the request. Return the structured result
only.
""".strip()

ANSWER_JUDGE_SCHEMA_VERSION = 2
EXTERNAL_ANSWER_JUDGE_SCHEMA_VERSION = 3


class GeneratedProfile(BaseModel):
    expertise: Literal["beginner", "intermediate", "experienced", "expert"]
    answer_length: Literal["concise", "moderate", "detailed"]
    tone: str
    explanation_style: str
    interests: list[str]
    preferred_travel_styles: list[str]
    preferred_activities: list[str]
    budget_level: str
    avoid: list[str]


class GeneratedMemory(BaseModel):
    memory_id: str
    key: str
    value: str


class GeneratedTurn(BaseModel):
    turn_id: int
    query: str
    intent: str
    operation: str
    query_constraints: list[PreferenceConstraint] = Field(default_factory=list)
    applicable_personalization: list[PreferenceConstraint] = Field(default_factory=list)
    relevant_memory_ids: list[str] = Field(default_factory=list)
    key_answer_facts: list[str] = Field(default_factory=list)
    difficulty: Literal["simple", "contextual", "complex"]


class GeneratedConversation(BaseModel):
    conversation_id: str
    turns: list[GeneratedTurn]


class GeneratedUser(BaseModel):
    user_id: str
    profile: GeneratedProfile
    memories: list[GeneratedMemory]
    conversations: list[GeneratedConversation]


class GeneratedEnvelope(BaseModel):
    user: GeneratedUser


class ChunkGrade(BaseModel):
    chunk_id: str
    relevance: int = Field(ge=0, le=3)


class RetrievalJudgment(BaseModel):
    judgments: list[ChunkGrade]

    @model_validator(mode="after")
    def validate_grades(self) -> "RetrievalJudgment":
        identifiers = [item.chunk_id for item in self.judgments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Retrieval judgment contains duplicate chunk IDs")
        return self


class AnswerRationale(BaseModel):
    correctness: str
    faithfulness: str
    personalization_adherence: str
    completeness: str


class AnswerScorePayload(BaseModel):
    correctness: float = Field(ge=1, le=5)
    faithfulness: float = Field(ge=1, le=5)
    personalization_adherence: float = Field(ge=1, le=5)
    completeness: float = Field(ge=1, le=5)
    rationale: AnswerRationale


class AnswerJudgment(BaseModel):
    answer_scores: AnswerScorePayload


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


def infer_legacy_operation(query: str, intent: str) -> str:
    text = query.casefold()
    if intent == "comparison" or any(token in text for token in ("compare", "comparison", " versus ", " vs ", "khác nhau")):
        return "compare"
    if intent == "itinerary" or any(token in text for token in ("itinerary", "plan a ", "lịch trình")):
        return "plan"
    if intent == "recommendation" or any(token in text for token in ("recommend", "suggest", "best ", "gợi ý")):
        return "recommend"
    if any(token in text for token in ("explain", "why ", "how does", "giải thích", "tại sao")):
        return "explain"
    return "lookup"


def migrate_legacy_intent(query: str, intent: str) -> str:
    if intent != "comparison":
        return intent
    text = query.casefold()
    if any(token in text for token in ("train", "bus", "flight", "car", "taxi", "transport", "tàu", "xe", "bay")):
        return "transport"
    if any(token in text for token in ("hotel", "hostel", "resort", "accommodation")):
        return "accommodation_search"
    if any(token in text for token in ("restaurant", "food", "dish", "cuisine")):
        return "food_search"
    return "recommendation"


def applicable_memory_ids(memories: list[dict], applicable: list[dict]) -> set[str]:
    return {
        memory["memory_id"]
        for memory in memories
        if memory.get("memory_id") and any(
            item.get("key") == memory.get("key")
            or item.get("value") == memory.get("value")
            for item in applicable
        )
    }


def openai_client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY in be/.env before running an OpenAI stage")
    return OpenAI(api_key=key, base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))


def json_completion(
    client: OpenAI,
    model: str,
    system: str,
    payload: dict,
    response_model: type[ResponseModel],
    max_tokens: int = 12000,
    attempts: int = 3,
) -> tuple[ResponseModel, dict]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format=response_model,
                max_completion_tokens=max_tokens,
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise ValueError(f"{model} returned no parsed structured output")
            metadata = {
                "response_id": response.id,
                "model": response.model,
                "usage": response.usage.model_dump() if response.usage else None,
            }
            normalized = normalize_usage(response)
            metadata["normalized_usage"] = normalized
            metadata["estimated_cost_usd"] = estimate_cost_usd(
                response.model or model,
                normalized,
                pricing_snapshot(),
            )
            return parsed, metadata
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"OpenAI structured request failed after {attempts} attempts: {last_error}") from last_error


def json_web_completion(
    client: OpenAI,
    model: str,
    system: str,
    payload: dict,
    response_model: type[ResponseModel],
    max_tokens: int = 3000,
    attempts: int = 3,
) -> tuple[ResponseModel, dict]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.responses.parse(
                model=model,
                instructions=system,
                input=json.dumps(payload, ensure_ascii=False),
                tools=[{"type": "web_search"}],
                tool_choice="required",
                reasoning={"effort": "low"},
                text_format=response_model,
                max_output_tokens=max_tokens,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError(f"{model} returned no parsed structured output")
            metadata = {
                "response_id": response.id,
                "model": response.model,
                "usage": (
                    response.usage.model_dump(warnings=False)
                    if response.usage else None
                ),
                "web_search_used": True,
            }
            normalized = normalize_usage(response)
            metadata["normalized_usage"] = normalized
            metadata["estimated_cost_usd"] = estimate_cost_usd(
                response.model or model,
                normalized,
                pricing_snapshot(),
            )
            return parsed, metadata
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(
        f"OpenAI structured web request failed after {attempts} attempts: {last_error}"
    ) from last_error


def generate_dataset(output: Path, users: int, conversations: int, turns: int) -> dict:
    client = openai_client()
    model = os.environ.get("DATASET_GENERATOR_MODEL", "gpt-5.6-luna")
    known_cities = get_known_cities()
    if not known_cities:
        raise RuntimeError("The corpus contains no known cities; ingest data before dataset generation")
    generated_users = []
    api_calls: list[dict] = []
    for index in range(1, users + 1):
        print(f"[generate {index}/{users}] user", flush=True)
        generation_payload = {
                "user_number": index,
                "required_user_id": f"USER-{index:02d}",
                "conversation_count": conversations,
                "turns_per_conversation": turns,
                "allowed_intents": ALLOWED_QUERY_INTENTS,
                "allowed_operations": ALLOWED_QUERY_OPERATIONS,
                "allowed_travel_styles": ALLOWED_TRAVEL_STYLES,
                "allowed_activities": ALLOWED_ACTIVITIES,
                "allowed_budget_levels": ALLOWED_BUDGET_LEVELS,
                "allowed_regions": ALLOWED_REGIONS,
                "allowed_place_types": ALLOWED_PLACE_TYPES,
                "allowed_suitable_for": ALLOWED_SUITABLE_FOR,
                "known_corpus_cities": known_cities,
                "diversity_instruction": "Make this user clearly different from the other benchmark users.",
        }
        last_validation_error: Exception | None = None
        for semantic_attempt in range(1, 4):
            result, call_metadata = json_completion(
                client,
                model,
                GENERATOR_SYSTEM,
                generation_payload,
                GeneratedEnvelope,
            )
            user = result.user.model_dump()
            try:
                validate_generated_user(
                    user,
                    expected_user_id=f"USER-{index:02d}",
                    expected_conversations=conversations,
                    expected_turns=turns,
                    known_cities=set(known_cities),
                )
                break
            except ValueError as exc:
                last_validation_error = exc
                api_calls.append({
                    "user_id": f"USER-{index:02d}",
                    "semantic_attempt": semantic_attempt,
                    "status": "rejected",
                    "reason": str(exc),
                    **call_metadata,
                })
        else:
            raise RuntimeError(
                f"Generator failed semantic validation after 3 attempts: {last_validation_error}"
            ) from last_validation_error
        api_calls.append({"user_id": user["user_id"], **call_metadata})
        generated_users.append(user)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "version": "1.4",
                    "generator_model": model,
                    "annotation_status": "llm_annotated",
                    "api_calls": api_calls,
                    "users": generated_users,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return json.loads(output.read_text(encoding="utf-8"))


def validate_generated_user(
    user: dict,
    expected_user_id: str,
    expected_conversations: int,
    expected_turns: int,
    known_cities: set[str],
) -> None:
    profile = user.get("profile") or {}
    checks = {
        "preferred_travel_styles": (profile.get("preferred_travel_styles") or [], set(ALLOWED_TRAVEL_STYLES)),
        "preferred_activities": (profile.get("preferred_activities") or [], set(ALLOWED_ACTIVITIES)),
    }
    errors = []
    if user.get("user_id") != expected_user_id:
        errors.append(f"user_id must be {expected_user_id!r}, got {user.get('user_id')!r}")
    for field, (values, allowed) in checks.items():
        invalid = [value for value in values if value not in allowed]
        if invalid:
            errors.append(f"{field}: {invalid}")
    budget = profile.get("budget_level")
    if budget not in ALLOWED_BUDGET_LEVELS:
        errors.append(f"budget_level: {budget!r}")
    for field in ["interests", "avoid"]:
        if not isinstance(profile.get(field), list) or not all(
            isinstance(value, str) for value in profile.get(field, [])
        ):
            errors.append(f"{field} must be an array of strings")
    constraint_vocabs = {
        "region": set(ALLOWED_REGIONS),
        "place_type": set(ALLOWED_PLACE_TYPES),
        "activity": set(ALLOWED_ACTIVITIES),
        "travel_style": set(ALLOWED_TRAVEL_STYLES),
        "suitable_for": set(ALLOWED_SUITABLE_FOR),
        "budget": set(ALLOWED_BUDGET_LEVELS),
    }
    allowed_constraint_keys = {
        "country", "region", "city", "province", "place_type", "activity",
        "travel_style", "suitable_for", "budget", "duration_days",
        "date_from", "date_to", "near_place", "max_distance_km",
    }
    memories = user.get("memories", [])
    memory_ids = [item.get("memory_id") for item in memories]
    if len(memory_ids) != len(set(memory_ids)):
        errors.append("memory_id values must be unique within a user")
    conversations = user.get("conversations", [])
    if len(conversations) != expected_conversations:
        errors.append(
            f"expected {expected_conversations} conversations, got {len(conversations)}"
        )
    conversation_ids = [item.get("conversation_id") for item in conversations]
    if len(conversation_ids) != len(set(conversation_ids)):
        errors.append("conversation_id values must be unique within a user")
    for conversation in conversations:
        conversation_turns = conversation.get("turns", [])
        if len(conversation_turns) != expected_turns:
            errors.append(
                f"{conversation.get('conversation_id')}: expected {expected_turns} turns, "
                f"got {len(conversation_turns)}"
            )
        turn_ids = [turn.get("turn_id") for turn in conversation_turns]
        if turn_ids != list(range(1, expected_turns + 1)):
            errors.append(
                f"{conversation.get('conversation_id')}: turn IDs must be sequential integers "
                f"1..{expected_turns}, got {turn_ids}"
            )
        for turn in conversation_turns:
            if not isinstance(turn.get("turn_id"), int):
                errors.append(f"turn_id must be an integer: {turn.get('turn_id')!r}")
            if turn.get("intent") not in ALLOWED_QUERY_INTENTS:
                errors.append(f"invalid intent: {turn.get('intent')!r}")
            if turn.get("operation") not in ALLOWED_QUERY_OPERATIONS:
                errors.append(f"invalid operation: {turn.get('operation')!r}")
            if not str(turn.get("query") or "").strip():
                errors.append(f"turn {turn.get('turn_id')} has an empty query")
            unknown_memories = set(turn.get("relevant_memory_ids", [])) - set(memory_ids)
            if unknown_memories:
                errors.append(
                    f"turn {turn.get('turn_id')} references unknown memories: {sorted(unknown_memories)}"
                )
            relevant_ids = set(turn.get("relevant_memory_ids", []))
            applicable = turn.get("applicable_personalization", [])
            expected_memory_ids = applicable_memory_ids(memories, applicable)
            missing_memory_ids = expected_memory_ids - relevant_ids
            if missing_memory_ids:
                errors.append(
                    f"turn {turn.get('turn_id')} omits applicable memories: "
                    f"{sorted(missing_memory_ids)}"
                )
            constraint_pairs = [
                (item.get("key"), str(item.get("value")))
                for item in turn.get("query_constraints", [])
            ]
            if len(constraint_pairs) != len(set(constraint_pairs)):
                errors.append(
                    f"turn {turn.get('turn_id')} contains duplicate query constraints"
                )
            for item in turn.get("query_constraints", []):
                if item.get("key") not in allowed_constraint_keys:
                    errors.append(f"invalid constraint key: {item.get('key')!r}")
                if (
                    item.get("key") == "place_type"
                    and item.get("value") in {"country", "city", "province", "region"}
                ):
                    errors.append(
                        "geographic type must use a location constraint, not "
                        f"place_type: {item.get('value')!r}"
                    )
                if item.get("key") == "city" and item.get("value") not in known_cities:
                    errors.append(f"unknown corpus city: {item.get('value')!r}")
                allowed = constraint_vocabs.get(item.get("key"))
                if allowed is not None and item.get("value") not in allowed:
                    errors.append(
                        f"invalid {item.get('key')}: {item.get('value')!r}"
                    )
    if errors:
        raise ValueError(
            f"Generated profile {user.get('user_id', '<unknown>')} violates config.vocab: "
            + "; ".join(errors)
        )


def chunk_id(document) -> str:
    return str(document.metadata.get("chunk_id") or document.metadata.get("id") or "")


def repair_mojibake(value):
    """Repair the common UTF-8-as-Windows-1252 corruption without touching clean text."""
    if isinstance(value, str) and any(marker in value for marker in ("Ã", "â€", "Â")):
        try:
            repaired = value.encode("cp1252").decode("utf-8")
            if repaired.count("�") <= value.count("�"):
                return repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    if isinstance(value, dict):
        return {key: repair_mojibake(item) for key, item in value.items()}
    if isinstance(value, list):
        return [repair_mojibake(item) for item in value]
    return value


def normalize_retrieved_documents(*groups) -> None:
    seen: set[int] = set()
    for documents in groups:
        for document in documents:
            if id(document) in seen:
                continue
            seen.add(id(document))
            document.page_content = repair_mojibake(document.page_content)
            document.metadata = repair_mojibake(document.metadata)


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BE_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_model_metadata() -> dict:
    embedding = get_embedding_model()
    reranker = get_reranker()
    return {
        "embedding": {
            "name": EMBEDDING_MODEL_NAME,
            "class": type(embedding).__name__,
            "dimension": embedding.get_sentence_embedding_dimension(),
            "max_sequence_length": getattr(embedding, "max_seq_length", None),
            "sentence_transformers_version": package_version("sentence-transformers"),
        },
        "reranker": {
            "name": RERANKER_MODEL_NAME,
            "class": type(reranker).__name__,
            "max_sequence_length": getattr(reranker, "max_length", None),
            "sentence_transformers_version": package_version("sentence-transformers"),
        },
    }


def corpus_metadata() -> dict:
    db = SessionLocal()
    try:
        rows = (
            db.query(
                RagChunkORM.id,
                RagChunkORM.document_id,
                RagChunkORM.chunk_hash,
                RagChunkORM.updated_at,
                RagChunkORM.embedding_model,
                RagChunkORM.embedding.is_not(None).label("has_embedding"),
            )
            .order_by(RagChunkORM.id)
            .all()
        )
        digest = hashlib.sha256()
        document_ids: set[str] = set()
        embedding_models: dict[str, int] = {}
        embedded_count = 0
        latest_updated_at = None
        for row in rows:
            chunk_id_value = str(row.id)
            document_id_value = str(row.document_id)
            updated_value = row.updated_at.isoformat() if row.updated_at else ""
            digest.update(
                f"{chunk_id_value}\x1f{row.chunk_hash}\x1f{updated_value}\n".encode("utf-8")
            )
            document_ids.add(document_id_value)
            if row.has_embedding:
                embedded_count += 1
            model_name = row.embedding_model or "unspecified"
            embedding_models[model_name] = embedding_models.get(model_name, 0) + 1
            if row.updated_at and (
                latest_updated_at is None or row.updated_at > latest_updated_at
            ):
                latest_updated_at = row.updated_at
        return {
            "fingerprint_algorithm": "sha256(chunk_id,chunk_hash,updated_at)",
            "fingerprint": digest.hexdigest(),
            "chunk_count": len(rows),
            "document_count": len(document_ids),
            "embedded_chunk_count": embedded_count,
            "embedding_model_counts": embedding_models,
            "latest_updated_at": (
                latest_updated_at.isoformat() if latest_updated_at else None
            ),
        }
    finally:
        db.close()


def serialize_document(document, rank: int) -> dict:
    return {
        "chunk_id": chunk_id(document),
        "rank": rank,
        "content": document.page_content,
        "metadata": document.metadata,
    }


def query_constraint_items(parsed) -> list[dict[str, str]]:
    return [item.model_dump() for item in parsed.explicit_constraints]


def execute_pipeline(
    dataset_path: Path,
    output: Path,
    limit: int | None,
    *,
    selected_case_ids: set[str] | None = None,
    context_cases: dict[str, dict] | None = None,
    use_external_web: bool = False,
) -> dict:
    source = json.loads(dataset_path.read_text(encoding="utf-8"))
    run = {
        "version": "2.5",
        "run_id": f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
        "pipeline_version": "personalized-rag-eval-v2.5",
        "git_commit": git_commit(),
        "generator_model": source.get("generator_model"),
        "generator_api_calls": (
            [] if selected_case_ids is not None else source.get("api_calls", [])
        ),
        "answer_model": DEEPSEEK_ANSWER_MODEL,
        "pipeline_models": {
            "fast": DEEPSEEK_FAST_MODEL,
            "reasoning": DEEPSEEK_REASONING_MODEL,
            "parser": DEEPSEEK_PARSER_MODEL,
            "retrieval_planner_checker": DEEPSEEK_RETRIEVAL_MODEL,
            "answer": DEEPSEEK_ANSWER_MODEL,
        },
        "started_at": datetime.now(timezone.utc).isoformat(),
        "timezone": os.environ.get("USER_TIMEZONE", "Asia/Ho_Chi_Minh"),
        "corpus_version": corpus_metadata(),
        "embedding_model": None,
        "reranker_model": None,
        "random_seed": 42,
        "experiment_variant": (
            "low_coverage_external_recovery"
            if selected_case_ids is not None and use_external_web
            else "standard"
        ),
        "selected_case_ids": sorted(selected_case_ids or []),
        "external_web_fallback_enabled": use_external_web,
        "external_web_model": (
            os.environ.get("OPENAI_WEB_SEARCH_MODEL", "gpt-5.6-luna")
            if use_external_web else None
        ),
        "pricing_snapshot": pricing_snapshot(),
        "prompt_versions": {
            "generator_sha256": prompt_hash(GENERATOR_SYSTEM),
            "retrieval_judge_sha256": prompt_hash(RETRIEVAL_JUDGE_SYSTEM),
            "answer_judge_sha256": prompt_hash(ANSWER_JUDGE_SYSTEM),
            "external_answer_judge_sha256": prompt_hash(
                EXTERNAL_ANSWER_JUDGE_SYSTEM
            ),
            "query_processing_source_sha256": file_hash(
                BE_ROOT / "services" / "query_processing.py"
            ),
            "planner_checker_source_sha256": file_hash(
                BE_ROOT / "services" / "agentic_retrieval.py"
            ),
            "answer_source_sha256": file_hash(
                BE_ROOT / "services" / "answer_pipeline.py"
            ),
        },
        "cases": [],
    }
    expected_queries = {
        f"{user['user_id']}-{conversation['conversation_id']}-T{turn['turn_id']:02d}": turn["query"]
        for user in source["users"]
        for conversation in user["conversations"]
        for turn in conversation["turns"]
        if selected_case_ids is None
        or f"{user['user_id']}-{conversation['conversation_id']}-T{turn['turn_id']:02d}"
        in selected_case_ids
    }
    if selected_case_ids is not None:
        missing_case_ids = selected_case_ids - set(expected_queries)
        if missing_case_ids:
            raise ValueError(
                "Selected case IDs were not found in the generated dataset: "
                + ", ".join(sorted(missing_case_ids))
            )
    if output.exists():
        try:
            existing_run = json.loads(output.read_text(encoding="utf-8"))
            existing_cases = existing_run.get("cases", [])
            if (
                existing_run.get("pipeline_version") == run["pipeline_version"]
                and existing_run.get("selected_case_ids") == run["selected_case_ids"]
                and existing_run.get("external_web_fallback_enabled")
                == run["external_web_fallback_enabled"]
                and all(
                    expected_queries.get(case.get("case_id")) == case.get("query")
                    for case in existing_cases
                )
            ):
                run = existing_run
                run.pop("finished_at", None)
                print(
                    f"[pipeline resume] Reusing {len(existing_cases)} completed cases",
                    flush=True,
                )
        except (OSError, json.JSONDecodeError):
            pass
    existing_by_case = {
        case["case_id"]: case for case in run.get("cases", [])
    }
    completed = 0
    load_models()
    loaded_model_metadata = runtime_model_metadata()
    run["embedding_model"] = loaded_model_metadata["embedding"]
    run["reranker_model"] = loaded_model_metadata["reranker"]
    try:
        for user in source["users"]:
            profile = user["profile"]
            memory = UserTravelMemory.model_validate({
                "expertise": profile.get("expertise"),
                "answer_length": profile.get("answer_length"),
                "tone": profile.get("tone"),
                "explanation_style": profile.get("explanation_style"),
                "interests": profile.get("interests", []),
                "preferred_travel_styles": profile.get("preferred_travel_styles", []),
                "preferred_activities": profile.get("preferred_activities", []),
                "budget_level": profile.get("budget_level"),
                "avoid": profile.get("avoid", []),
                "personal_facts": [
                    item.get("value")
                    for item in user.get("memories", [])
                    if item.get("value")
                ],
            })
            memory_ids = [item["memory_id"] for item in user.get("memories", [])]
            for conversation in user["conversations"]:
                history: list[dict[str, str]] = []
                conversation_state = ConversationState()
                for turn in conversation["turns"]:
                    case_id = f"{user['user_id']}-{conversation['conversation_id']}-T{turn['turn_id']:02d}"
                    if selected_case_ids is not None and case_id not in selected_case_ids:
                        continue
                    if limit is not None and completed >= limit:
                        run["finished_at"] = datetime.now(timezone.utc).isoformat()
                        output.write_text(
                            json.dumps(run, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8",
                        )
                        return run
                    completed += 1
                    if selected_case_ids is not None:
                        baseline = (context_cases or {}).get(case_id)
                        if baseline is None:
                            raise ValueError(
                                f"Missing baseline context for selected case {case_id}"
                            )
                        history = list(baseline.get("conversation_history") or [])
                        conversation_state = ConversationState.model_validate(
                            baseline.get("conversation_state_before") or {}
                        )
                    existing_case = existing_by_case.get(case_id)
                    if existing_case is not None:
                        print(
                            f"[pipeline {completed}] {case_id} (resume: already complete)",
                            flush=True,
                        )
                        answer = existing_case.get("final_answer", "")
                        history.extend([
                            {"role": "user", "content": turn["query"]},
                            {"role": "assistant", "content": answer},
                        ])
                        try:
                            conversation_state = ConversationState.model_validate(
                                existing_case.get("conversation_state_after", {})
                            )
                        except Exception as exc:
                            print(
                                f"[PIPELINE RESUME WARNING] Invalid saved state for "
                                f"{case_id}: {exc}",
                                flush=True,
                            )
                        continue
                    inferred_memory_ids = applicable_memory_ids(
                        user.get("memories", []),
                        turn.get("applicable_personalization", []),
                    )
                    relevant_memory_ids = sorted({
                        *turn.get("relevant_memory_ids", []),
                        *inferred_memory_ids,
                    })
                    reference_operation = turn.get("operation") or infer_legacy_operation(
                        turn["query"], turn.get("intent", "")
                    )
                    reference_intent = migrate_legacy_intent(
                        turn["query"], turn.get("intent", "travel_information")
                    )
                    reference_constraints, reference_facets = split_reference_constraints(
                        turn.get("query_constraints", [])
                    )
                    print(f"[pipeline {completed}] {case_id}", flush=True)
                    telemetry, telemetry_token = activate_telemetry(case_id)
                    stage_events: list[dict] = []
                    started = perf_counter()
                    retrieval_history = list(history)
                    if conversation_state.summary:
                        retrieval_history.append({
                            "role": "system",
                            "content": (
                                "Current conversation trip context: "
                                + json.dumps(conversation_state.model_dump(), ensure_ascii=False)
                            ),
                        })
                    artifacts = run_retrieval_pipeline(
                        query=turn["query"],
                        conversation_history=retrieval_history,
                        user_id=None,
                        memory_override=memory,
                        progress_callback=lambda stage, data: stage_events.append({"stage": stage, "data": data}),
                    )
                    normalize_retrieved_documents(
                        artifacts.vector_docs,
                        artifacts.bm25_docs,
                        artifacts.candidates,
                        artifacts.reranked_docs,
                        artifacts.recovery_docs,
                    )
                    evidence = build_evidence(artifacts.reranked_docs)
                    external_result = None
                    response_mode = "internal_answer"
                    if use_external_web and not artifacts.coverage.sufficient:
                        external_result = generate_external_web_answer(
                            query=turn["query"],
                            rewritten_query=artifacts.rewritten_query,
                            missing_requirements=artifacts.coverage.missing_requirements,
                            evidence=evidence,
                            parsed=artifacts.parsed,
                            memory=memory,
                            conversation_memory=conversation_state,
                        )
                    if external_result is not None and external_result.succeeded:
                        answer = external_result.answer or ""
                        response_mode = "external_answer"
                    elif (
                        external_result is not None
                        and external_result.status == "clarification_required"
                    ):
                        answer = (
                            external_result.clarification_question
                            or "Please choose which current-information group to check first."
                        )
                        response_mode = "clarification_required"
                    else:
                        answer = generate_answer(
                            query=turn["query"],
                            rewritten_query=artifacts.rewritten_query,
                            parsed=artifacts.parsed,
                            evidence=evidence,
                            conversation_history=history,
                            memory=memory,
                            conversation_memory=conversation_state,
                            coverage=artifacts.coverage,
                            answer_readiness=artifacts.answer_readiness,
                        )
                    next_conversation_state = derive_conversation_state(
                        previous=conversation_state,
                        user_message=turn["query"],
                        assistant_message=answer,
                        current_date=date.today(),
                        timezone_name=os.environ.get("USER_TIMEZONE", "Asia/Ho_Chi_Minh"),
                    )
                    telemetry_snapshot = telemetry.snapshot()
                    deactivate_telemetry(telemetry_token)
                    groups = {
                        "vector": artifacts.vector_docs,
                        "bm25": artifacts.bm25_docs,
                        "fusion": artifacts.candidates,
                        "reranked": artifacts.reranked_docs,
                        "recovery": artifacts.recovery_docs,
                    }
                    run["cases"].append({
                        "case_id": case_id,
                        "user_id": user["user_id"],
                        "conversation_id": conversation["conversation_id"],
                        "turn_id": turn["turn_id"],
                        "query": turn["query"],
                        "conversation_history": list(history),
                        "conversation_state_before": conversation_state.model_dump(),
                        "conversation_state_after": next_conversation_state.model_dump(),
                        "user_profile": profile,
                        "user_memories": user.get("memories", []),
                        "all_memory_ids": memory_ids,
                        "reference": {
                            "intent": reference_intent,
                            "operation": reference_operation,
                            "query_constraints": reference_constraints,
                            "retrieval_facets": reference_facets,
                            "applicable_personalization": turn.get("applicable_personalization", []),
                            "relevant_memory_ids": relevant_memory_ids,
                            "key_answer_facts": turn.get("key_answer_facts", []),
                        },
                        "understanding": {
                            "intent": (
                                artifacts.parsed.raw_intent
                                if artifacts.parsed.raw_intent is not None
                                else (
                                    "__parser_fallback__"
                                    if artifacts.parsed.parser_used_fallback
                                    else (artifacts.parsed.intent or "")
                                )
                            ),
                            "operation": (
                                artifacts.parsed.raw_operation
                                if artifacts.parsed.raw_operation is not None
                                else (
                                    "__parser_fallback__"
                                    if artifacts.parsed.parser_used_fallback
                                    else (artifacts.parsed.operation or "lookup")
                                )
                            ),
                            "query_constraints": parsed_hard_constraint_items(
                                artifacts.parsed
                            ),
                            "explicit_constraints": query_constraint_items(artifacts.parsed),
                            "retrieval_facets": {
                                "location": artifacts.parsed.location.model_dump(),
                                "place_types": artifacts.parsed.place_types,
                                "activities": artifacts.parsed.activities,
                                "travel_styles": artifacts.parsed.travel_styles,
                                "suitable_for": artifacts.parsed.suitable_for,
                                "constraints": artifacts.parsed.constraints.model_dump(),
                            },
                            "retrieval_facet_items": parsed_retrieval_facet_items(
                                artifacts.parsed
                            ),
                            "rewritten_query": artifacts.rewritten_query,
                            "parsed_query": artifacts.parsed.model_dump(),
                            "plan": artifacts.plan.model_dump(),
                        },
                        "retrieval": {
                            "stages": {
                                name: [serialize_document(doc, rank) for rank, doc in enumerate(docs, 1)]
                                for name, docs in groups.items()
                            },
                            "selected_evidence_ids": [chunk_id(doc) for doc in artifacts.reranked_docs],
                            "coverage_before_recovery": artifacts.initial_coverage.model_dump(),
                            "coverage_after_recovery": artifacts.coverage.model_dump(),
                            "coverage_check": artifacts.coverage.model_dump(),
                            "comparison_balance": artifacts.comparison_balance,
                            "filter_relaxations": artifacts.filter_relaxations,
                            "recovery_effectiveness": artifacts.recovery_effectiveness,
                            "answer_readiness": artifacts.answer_readiness.model_dump(),
                            "confidence": artifacts.confidence.model_dump(),
                            "external_recovery": (
                                {
                                    "status": external_result.status,
                                    "model": external_result.model,
                                    "answer_generated": external_result.succeeded,
                                    "sources": [
                                        source.to_storage_dict()
                                        for source in external_result.sources
                                    ],
                                    "requirements": [
                                        requirement.to_storage_dict()
                                        for requirement in external_result.requirements
                                    ],
                                    "clarification_options": (
                                        external_result.clarification_options
                                    ),
                                    "error_type": external_result.error_type,
                                }
                                if external_result is not None
                                else {
                                    "status": "not_attempted",
                                    "answer_generated": False,
                                }
                            ),
                        },
                        "final_answer": answer,
                        "response_mode": response_mode,
                        "pipeline_events": stage_events,
                        "timings": {**artifacts.timings.__dict__, "case_wall_ms": round((perf_counter() - started) * 1000, 3)},
                        "llm_telemetry": telemetry_snapshot,
                    })
                    history.extend([{"role": "user", "content": turn["query"]}, {"role": "assistant", "content": answer}])
                    conversation_state = next_conversation_state
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(json.dumps(run, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    finally:
        unload_models()
    run["finished_at"] = datetime.now(timezone.utc).isoformat()
    output.write_text(
        json.dumps(run, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return run


def unique_candidates(case: dict, maximum: int = 50) -> list[dict]:
    pool: dict[str, dict] = {}
    for stage in ["reranked", "fusion", "recovery", "vector", "bm25"]:
        for item in case["retrieval"]["stages"].get(stage, []):
            if item["chunk_id"] and item["chunk_id"] not in pool:
                pool[item["chunk_id"]] = {
                    "chunk_id": item["chunk_id"],
                    "content": item["content"][:1600],
                    "place_name": item["metadata"].get("place_name"),
                    "city": item["metadata"].get("city"),
                }
            if len(pool) >= maximum:
                candidates = list(pool.values())
                random.Random(case["case_id"]).shuffle(candidates)
                return candidates
    candidates = list(pool.values())
    random.Random(case["case_id"]).shuffle(candidates)
    return candidates


def judge_run(pipeline_path: Path, output: Path, limit: int | None) -> dict:
    source = json.loads(pipeline_path.read_text(encoding="utf-8"))
    client = openai_client()
    model = os.environ.get("JUDGE_MODEL", "gpt-5.6-terra")
    judged = {**source, "judge_model": model, "cases": []}
    if output.exists():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
            if (
                existing.get("run_id") == source.get("run_id")
                and existing.get("pipeline_version") == source.get("pipeline_version")
                and existing.get("judge_model") == model
            ):
                judged = existing
        except (OSError, json.JSONDecodeError):
            pass
    # Keep both judge prompt versions in resumed artifacts. External-answer
    # cases use a web-enabled judge and must not be attributed to the standard
    # internal-evidence-only prompt.
    judged.setdefault("prompt_versions", {})[
        "external_answer_judge_sha256"
    ] = prompt_hash(EXTERNAL_ANSWER_JUDGE_SYSTEM)
    existing_by_case = {
        case["case_id"]: case
        for case in judged.get("cases", [])
    }
    judged_by_case: dict[str, dict] = {}
    for index, case in enumerate(source["cases"][:limit], 1):
        existing_case = existing_by_case.get(case["case_id"], {})
        retrieval_complete = bool(
            existing_case.get("reference", {}).get("relevance_grades")
        )
        external_answer = case.get("response_mode") == "external_answer"
        expected_answer_schema = (
            EXTERNAL_ANSWER_JUDGE_SCHEMA_VERSION
            if external_answer else ANSWER_JUDGE_SCHEMA_VERSION
        )
        answer_complete = bool(
            existing_case.get("final_answer_scores")
            and existing_case.get("answer_judge_schema_version")
            == expected_answer_schema
        )
        if retrieval_complete and answer_complete:
            judged_by_case[case["case_id"]] = existing_case
            print(
                f"[judge {index}/{min(len(source['cases']), limit or len(source['cases']))}] "
                f"{case['case_id']} (resume: already complete)",
                flush=True,
            )
            continue
        print(f"[judge {index}/{min(len(source['cases']), limit or len(source['cases']))}] {case['case_id']}", flush=True)
        if retrieval_complete:
            relevance = existing_case["reference"]["relevance_grades"]
            retrieval_call = existing_case.get("judge_api_calls", {}).get("retrieval")
            candidate_key_to_chunk_id = existing_case.get(
                "judge_api_calls", {}
            ).get("retrieval_candidate_id_map", {})
        else:
            candidates = unique_candidates(case)
            candidate_key_to_chunk_id = {
                f"C{candidate_index:03d}": item["chunk_id"]
                for candidate_index, item in enumerate(candidates, 1)
            }
            judge_candidates = [
                {**item, "chunk_id": candidate_key}
                for candidate_key, item in zip(
                    candidate_key_to_chunk_id, candidates, strict=True
                )
            ]
            retrieval_result, retrieval_call = json_completion(
                client, model, RETRIEVAL_JUDGE_SYSTEM,
                {
                    "query": case["query"],
                    "conversation_history": case["conversation_history"],
                    "expected_intent": case["reference"]["intent"],
                    "expected_operation": case["reference"]["operation"],
                    "expected_query_constraints": case["reference"]["query_constraints"],
                    "expected_retrieval_facets": case["reference"].get("retrieval_facets", []),
                    "candidate_chunks": judge_candidates,
                },
                RetrievalJudgment,
                max_tokens=7000,
            )
            candidate_keys = set(candidate_key_to_chunk_id)
            relevance_by_key = {
                item.chunk_id: item.relevance
                for item in retrieval_result.judgments
            }
            returned_keys = set(relevance_by_key)
            if returned_keys != candidate_keys:
                raise ValueError(
                    "Retrieval judge candidate coverage mismatch: "
                    f"missing={sorted(candidate_keys - returned_keys)}, "
                    f"extra={sorted(returned_keys - candidate_keys)}"
                )
            relevance = {
                candidate_key_to_chunk_id[key]: grade
                for key, grade in relevance_by_key.items()
            }
        selected_evidence = [
            {
                "evidence_id": f"E{evidence_index}",
                "chunk_id": item["chunk_id"],
                "place_name": item.get("metadata", {}).get("place_name"),
                "city": item.get("metadata", {}).get("city"),
                "content": item["content"],
            }
            for evidence_index, item in enumerate(
                case["retrieval"]["stages"]["reranked"], 1
            )
        ]
        answer_payload = {
                "query": case["query"],
                "conversation_history": case["conversation_history"],
                "user_profile": case["user_profile"],
                "relevant_user_memories": [
                    memory
                    for memory in case.get("user_memories", [])
                    if memory.get("memory_id") in set(case["reference"]["relevant_memory_ids"])
                ],
                "expected_intent": case["reference"]["intent"],
                "expected_operation": case["reference"]["operation"],
                "expected_query_constraints": case["reference"]["query_constraints"],
                "expected_retrieval_facets": case["reference"].get(
                    "retrieval_facets", []
                ),
                "applicable_personalization": case["reference"]["applicable_personalization"],
                "expected_answer_criteria": case["reference"]["key_answer_facts"],
                "selected_evidence": selected_evidence,
                "answer": case["final_answer"],
        }
        if external_answer:
            external_recovery = case.get("retrieval", {}).get(
                "external_recovery", {}
            )
            answer_payload["external_sources"] = external_recovery.get(
                "sources", []
            )
            answer_payload["external_requirements"] = external_recovery.get(
                "requirements", []
            )
            answer_result, answer_call = json_web_completion(
                client,
                model,
                EXTERNAL_ANSWER_JUDGE_SYSTEM,
                answer_payload,
                AnswerJudgment,
                max_tokens=3000,
            )
        else:
            answer_result, answer_call = json_completion(
                client,
                model,
                ANSWER_JUDGE_SYSTEM,
                answer_payload,
                AnswerJudgment,
                max_tokens=1800,
            )
        scores = FinalAnswerScores.model_validate({
            **answer_result.answer_scores.model_dump(),
            "judge_model": model,
        })
        case["reference"]["relevance_grades"] = relevance
        case["final_answer_scores"] = scores.model_dump()
        case["answer_judge_schema_version"] = expected_answer_schema
        case["judge_api_calls"] = {
            "retrieval": retrieval_call,
            "answer": answer_call,
            "retrieval_candidate_id_map": candidate_key_to_chunk_id,
        }
        judged_by_case[case["case_id"]] = case
        judged["cases"] = [
            judged_by_case[source_case["case_id"]]
            for source_case in source["cases"][:limit]
            if source_case["case_id"] in judged_by_case
        ]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(judged, ensure_ascii=False, indent=2), encoding="utf-8")
    # A final resumed case reaches `continue` before the per-case checkpoint
    # write. Always rebuild and persist the complete ordered case list once
    # after the loop so resume cannot silently drop the last case.
    judged["cases"] = [
        judged_by_case[source_case["case_id"]]
        for source_case in source["cases"][:limit]
        if source_case["case_id"] in judged_by_case
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(judged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return judged


def export_thesis_dataset(judged_path: Path, output: Path) -> ThesisDataset:
    source = json.loads(judged_path.read_text(encoding="utf-8"))
    cases = []
    for case in source["cases"]:
        reranked = case["retrieval"]["stages"]["reranked"]
        payload = {
            "case_id": case["case_id"],
            "user_id": case["user_id"],
            "conversation_id": case["conversation_id"],
            "turn_id": case["turn_id"],
            "query": case["query"],
            "conversation_history": case["conversation_history"],
            "user_profile": case["user_profile"],
            "user_memories": case.get("user_memories", []),
            "annotation_status": "llm_annotated",
            "reference": case["reference"],
            "prediction": {
                "understanding": {
                    "intent": case["understanding"]["intent"],
                    "operation": case["understanding"]["operation"],
                    "query_constraints": case["understanding"]["query_constraints"],
                    "retrieval_facets": case["understanding"].get(
                        "retrieval_facet_items", []
                    ),
                },
                "retrieval": {
                    "retrieved_chunk_ids": [item["chunk_id"] for item in reranked],
                    "selected_evidence_ids": case["retrieval"]["selected_evidence_ids"],
                    "evidence": {item["chunk_id"]: item["content"] for item in reranked},
                },
                "final_answer": case["final_answer"],
                "final_answer_scores": case["final_answer_scores"],
            },
        }
        cases.append(ThesisEvaluationCase.model_validate(payload))
    dataset = ThesisDataset(cases=cases)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")
    return dataset


def aggregate_openai_usage(source: dict) -> dict[str, int]:
    totals: dict[str, int] = {}

    def visit(value) -> None:
        if isinstance(value, dict):
            usage = value.get("usage")
            if isinstance(usage, dict):
                for key, amount in usage.items():
                    if isinstance(amount, int):
                        totals[key] = totals.get(key, 0) + amount
            for key, nested in value.items():
                if key != "usage":
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(source.get("generator_api_calls", []))
    visit([case.get("judge_api_calls", {}) for case in source.get("cases", [])])
    return totals


def aggregate_pipeline_telemetry(source: dict) -> dict:
    cases = source.get("cases", [])
    token_keys = [
        "input_tokens", "cached_input_tokens", "uncached_input_tokens",
        "output_tokens", "total_tokens",
    ]
    token_totals = {key: 0 for key in token_keys}
    stage_totals: dict[str, dict] = {}
    latencies = []
    known_costs = []
    for case in cases:
        telemetry = case.get("llm_telemetry") or {}
        totals = telemetry.get("totals") or {}
        for key in token_keys:
            token_totals[key] += int(totals.get(key, 0) or 0)
        if telemetry.get("estimated_cost_usd") is not None:
            known_costs.append(float(telemetry["estimated_cost_usd"]))
        case_latency = case.get("timings", {}).get("case_wall_ms")
        if case_latency is not None:
            latencies.append(float(case_latency))
        for record in telemetry.get("stages", []):
            stage = record["stage"]
            aggregate = stage_totals.setdefault(stage, {
                "call_count": 0, "latency_ms": 0.0, "total_tokens": 0,
                "estimated_cost_usd": 0.0, "cost_available": True,
            })
            aggregate["call_count"] += 1
            aggregate["latency_ms"] += float(record.get("latency_ms", 0) or 0)
            aggregate["total_tokens"] += int(record.get("total_tokens", 0) or 0)
            if record.get("estimated_cost_usd") is None:
                aggregate["cost_available"] = False
            else:
                aggregate["estimated_cost_usd"] += float(record["estimated_cost_usd"])
    for aggregate in stage_totals.values():
        aggregate["latency_ms"] = round(aggregate["latency_ms"], 3)
        aggregate["estimated_cost_usd"] = (
            round(aggregate["estimated_cost_usd"], 10)
            if aggregate.pop("cost_available") else None
        )
    sorted_latencies = sorted(latencies)
    latency_summary = {
        "mean": sum(latencies) / len(latencies),
        "median": sorted_latencies[len(sorted_latencies) // 2],
        "p95": sorted_latencies[max(0, math.ceil(0.95 * len(sorted_latencies)) - 1)],
        "min": sorted_latencies[0],
        "max": sorted_latencies[-1],
    } if latencies else {}
    return {
        "token_usage": token_totals,
        "estimated_cost_usd": round(sum(known_costs), 10) if known_costs else None,
        "latency_summary_ms": latency_summary,
        "by_stage": stage_totals,
    }


def aggregate_experiment_cost(source: dict) -> dict:
    generator_costs = [
        call.get("estimated_cost_usd")
        for call in source.get("generator_api_calls", [])
        if call.get("estimated_cost_usd") is not None
    ]
    judge_costs = [
        call.get("estimated_cost_usd")
        for case in source.get("cases", [])
        for call in (case.get("judge_api_calls") or {}).values()
        if call.get("estimated_cost_usd") is not None
    ]
    pipeline = aggregate_pipeline_telemetry(source).get("estimated_cost_usd")
    generation = sum(generator_costs) if generator_costs else None
    judging = sum(judge_costs) if judge_costs else None
    known = [value for value in (generation, pipeline, judging) if value is not None]
    return {
        "generation": round(generation, 10) if generation is not None else None,
        "pipeline": pipeline,
        "judging": round(judging, 10) if judging is not None else None,
        "total": round(sum(known), 10) if known else None,
        "mean_per_case": round(sum(known) / len(source.get("cases", [])), 10)
        if known and source.get("cases") else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI generation -> RAG pipeline -> OpenAI judge")
    parser.add_argument(
        "--stage",
        choices=["generate", "pipeline", "judge", "export", "evaluate", "all"],
        default="all",
    )
    parser.add_argument("--work-dir", type=Path, default=Path(__file__).parent / "runs" / "openai_experiment")
    parser.add_argument(
        "--dataset-path",
        type=Path,
        help="Reuse an existing generated dataset instead of work-dir/01_generated_dataset.json.",
    )
    parser.add_argument(
        "--case-ids-file",
        type=Path,
        help="Run only these case IDs, one per line.",
    )
    parser.add_argument(
        "--context-run",
        type=Path,
        help="Baseline pipeline or judged run used to restore selected-case context.",
    )
    parser.add_argument(
        "--external-web",
        action="store_true",
        help="Enable freshness-aware external recovery for uncovered requirements.",
    )
    parser.add_argument("--users", type=int, default=5)
    parser.add_argument("--conversations", type=int, default=2)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    generated = args.dataset_path or args.work_dir / "01_generated_dataset.json"
    pipeline = args.work_dir / "02_pipeline_traces.json"
    judged = args.work_dir / "03_judged_traces.json"
    thesis = args.work_dir / "04_thesis_dataset.json"

    if args.stage in {"generate", "all"}:
        generate_dataset(generated, args.users, args.conversations, args.turns)
    selected_case_ids = None
    if args.case_ids_file:
        selected_case_ids = {
            line.strip()
            for line in args.case_ids_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        if not selected_case_ids:
            raise ValueError("--case-ids-file did not contain any case IDs")
        if not args.context_run:
            raise ValueError("--context-run is required with --case-ids-file")
    context_cases = None
    if args.context_run:
        context_source = json.loads(args.context_run.read_text(encoding="utf-8"))
        context_cases = {
            case["case_id"]: case for case in context_source.get("cases", [])
        }

    if args.stage in {"pipeline", "evaluate", "all"}:
        execute_pipeline(
            generated,
            pipeline,
            args.limit,
            selected_case_ids=selected_case_ids,
            context_cases=context_cases,
            use_external_web=args.external_web,
        )
    if args.stage in {"judge", "evaluate", "all"}:
        judge_run(pipeline, judged, args.limit)
    if args.stage in {"export", "evaluate", "all"}:
        dataset = export_thesis_dataset(judged, thesis)
        rows = []
        for case in dataset.cases:
            row = deterministic_metrics(case)
            scores = case.prediction.final_answer_scores
            if scores:
                row.update(scores.model_dump(exclude={"rationale", "judge_model"}))
            rows.append(row)
        summary = {
            key: sum(row[key] for row in rows) / len(rows)
            for key in rows[0]
        } if rows else {}
        judged_source = json.loads(judged.read_text(encoding="utf-8"))
        response_mode_counts: dict[str, int] = {}
        completed_answer_rows = []
        for case, row in zip(judged_source.get("cases", []), rows):
            response_mode = case.get("response_mode", "internal_answer")
            response_mode_counts[response_mode] = (
                response_mode_counts.get(response_mode, 0) + 1
            )
            if response_mode != "clarification_required":
                completed_answer_rows.append(row)
        completed_answer_metric_means = {
            key: sum(row[key] for row in completed_answer_rows)
            / len(completed_answer_rows)
            for key in completed_answer_rows[0]
        } if completed_answer_rows else {}
        external_recovery_status_counts: dict[str, int] = {}
        for case in judged_source.get("cases", []):
            status = (
                case.get("retrieval", {})
                .get("external_recovery", {})
                .get("status", "not_recorded")
            )
            external_recovery_status_counts[status] = (
                external_recovery_status_counts.get(status, 0) + 1
            )
        pipeline_telemetry = aggregate_pipeline_telemetry(judged_source)
        summary_payload = {
            "metric_means": summary,
            "completed_answer_metric_means": completed_answer_metric_means,
            "case_count": len(rows),
            "completed_answer_count": len(completed_answer_rows),
            "response_mode_counts": response_mode_counts,
            "external_recovery_status_counts": external_recovery_status_counts,
            "coverage_sufficient_rate": (
                sum(
                    bool(case.get("retrieval", {}).get("coverage_check", {}).get("sufficient"))
                    for case in judged_source.get("cases", [])
                ) / len(judged_source.get("cases", []))
                if judged_source.get("cases") else 0.0
            ),
            "generator_model": judged_source.get("generator_model"),
            "answer_model": judged_source.get("answer_model"),
            "judge_model": judged_source.get("judge_model"),
            "pipeline_version": judged_source.get("pipeline_version"),
            "git_commit": judged_source.get("git_commit"),
            "corpus_version": judged_source.get("corpus_version"),
            "embedding_model": judged_source.get("embedding_model"),
            "reranker_model": judged_source.get("reranker_model"),
            "prompt_versions": judged_source.get("prompt_versions"),
            "openai_usage": aggregate_openai_usage(judged_source),
            "pipeline_token_usage": pipeline_telemetry["token_usage"],
            "latency_summary_ms": pipeline_telemetry["latency_summary_ms"],
            "telemetry_by_stage": pipeline_telemetry["by_stage"],
            "estimated_cost_usd": aggregate_experiment_cost(judged_source),
            "pricing_snapshot": judged_source.get("pricing_snapshot"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        (args.work_dir / "05_metric_summary.json").write_text(
            json.dumps(summary_payload, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary_payload, indent=2))


if __name__ == "__main__":
    main()
