from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from data_building.extract_metadata.extractor import (
    DEEPSEEK_FAST_MODEL,
    get_deepseek_client,
)
from services.llm_telemetry import create_chat_completion
from data_building.extract_metadata.helpers import extract_json_from_text
from config.vocab import (
    ALLOWED_ACTIVITIES,
    ALLOWED_BUDGET_LEVELS,
    ALLOWED_TRAVEL_STYLES,
)
from db.full_model import UserMemoryORM
from db.session import SessionLocal
from schemas.pipeline import UserTravelMemory


MemoryType = Literal[
    "travel_style",
    "activity",
    "budget",
    "avoid",
    "constraint",
    "interest",
    "expertise",
    "answer_length",
    "tone",
    "explanation_style",
    "personal_fact",
]


SINGLE_VALUE_MEMORY_TYPES = {
    "budget",
    "expertise",
    "answer_length",
    "tone",
    "explanation_style",
}

PROFILE_MEMORY_TYPES = {
    "travel_style",
    "activity",
    "budget",
    "avoid",
    "interest",
    "expertise",
    "answer_length",
    "tone",
    "explanation_style",
    "personal_fact",
}


class ExtractedMemory(BaseModel):
    memory_type: MemoryType
    content: str = Field(min_length=1, max_length=200)
    importance: float = Field(default=0.7, ge=0, le=1)


class MemoryExtraction(BaseModel):
    memories: list[ExtractedMemory] = Field(default_factory=list)


def extract_memories(message: str) -> list[ExtractedMemory]:
    client = get_deepseek_client()
    response = create_chat_completion(
        "memory_extraction", client,
        model=DEEPSEEK_FAST_MODEL,
        messages=[
            {
                "role": "system",
                "content": f"""
You extract explicit, durable travel preferences for personalization.

Return JSON only in this shape:
{{"memories":[{{"memory_type":"travel_style|activity|budget|avoid|constraint|interest|expertise|answer_length|tone|explanation_style|personal_fact","content":"short normalized value","importance":0.0}}]}}

Save only information the user explicitly states about themselves that is likely useful in future trips.
Examples: preferred travel style, favorite activity, usual budget, things they avoid, durable
accessibility or dietary constraints, desired answer length or tone, travel expertise, interests,
and non-sensitive personal facts that materially improve future travel answers.

Do not save:
- the current destination, dates, itinerary, or one-time request
- facts merely mentioned in a question
- guesses or inferred preferences
- names, email, address, credentials, identifiers, or payment data
- medical details, religion, politics, sexuality, ethnicity, or other sensitive personal data
- anything said by the assistant

Use an empty memories list when there is no safe durable preference.
Keep content concise and standalone. Use lowercase snake_case for simple labels when possible.
For travel_style use only: {", ".join(ALLOWED_TRAVEL_STYLES)}.
For activity use only: {", ".join(ALLOWED_ACTIVITIES)}.
For budget use only: {", ".join(ALLOWED_BUDGET_LEVELS)}.
""".strip(),
            },
            {
                "role": "user",
                "content": message,
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=400,
    )
    content = response.choices[0].message.content
    if not content:
        return []
    parsed = extract_json_from_text(content)
    memories = MemoryExtraction.model_validate(parsed).memories
    allowed_by_type = {
        "travel_style": set(ALLOWED_TRAVEL_STYLES),
        "activity": set(ALLOWED_ACTIVITIES),
        "budget": set(ALLOWED_BUDGET_LEVELS),
    }
    return [
        memory for memory in memories
        if memory.memory_type not in allowed_by_type
        or memory.content in allowed_by_type[memory.memory_type]
    ]


def save_memories(user_id: str, memories: list[ExtractedMemory]) -> None:
    if not memories:
        return
    db = SessionLocal()
    try:
        for memory in memories:
            normalized = " ".join(memory.content.strip().split()).lower()
            if not normalized:
                continue
            if memory.memory_type in SINGLE_VALUE_MEMORY_TYPES:
                db.query(UserMemoryORM).filter(
                    UserMemoryORM.user_id == user_id,
                    UserMemoryORM.memory_type == memory.memory_type,
                    UserMemoryORM.is_active.is_(True),
                ).update({"is_active": False})
            existing = db.scalar(
                select(UserMemoryORM).where(
                    UserMemoryORM.user_id == user_id,
                    UserMemoryORM.memory_type == memory.memory_type,
                    func.lower(UserMemoryORM.content) == normalized,
                )
            )
            if existing:
                existing.is_active = True
                existing.importance = max(existing.importance or 0, memory.importance)
                existing.updated_at = datetime.utcnow()
            else:
                db.add(
                    UserMemoryORM(
                        user_id=user_id,
                        memory_type=memory.memory_type,
                        content=normalized,
                        importance=memory.importance,
                        is_active=True,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def analyze_and_save_user_memory(user_id: str, message: str) -> None:
    try:
        save_memories(user_id, extract_memories(message))
    except Exception as exc:
        print(f"[USER MEMORY EXTRACTION FAILED] {exc}")


def profile_to_memories(
    profile: dict,
    personal_facts: list[str] | None = None,
) -> list[ExtractedMemory]:
    """Convert a structured travel profile into normalized database memories."""
    memories: list[ExtractedMemory] = []
    scalar_fields = {
        "expertise": "expertise",
        "answer_length": "answer_length",
        "tone": "tone",
        "explanation_style": "explanation_style",
        "budget_level": "budget",
    }
    list_fields = {
        "interests": "interest",
        "preferred_travel_styles": "travel_style",
        "preferred_activities": "activity",
        "avoid": "avoid",
    }
    for field, memory_type in scalar_fields.items():
        value = profile.get(field)
        if value:
            memories.append(ExtractedMemory(
                memory_type=memory_type,
                content=str(value),
                importance=0.8,
            ))
    for field, memory_type in list_fields.items():
        for value in profile.get(field) or []:
            if value:
                memories.append(ExtractedMemory(
                    memory_type=memory_type,
                    content=str(value),
                    importance=0.75,
                ))
    for fact in personal_facts or []:
        if fact:
            memories.append(ExtractedMemory(
                memory_type="personal_fact",
                content=str(fact),
                importance=0.65,
            ))
    return memories


def save_user_profile_memories(
    user_id: str,
    profile: dict,
    personal_facts: list[str] | None = None,
) -> None:
    memories = profile_to_memories(profile, personal_facts)
    db = SessionLocal()
    try:
        db.query(UserMemoryORM).filter(
            UserMemoryORM.user_id == user_id,
            UserMemoryORM.memory_type.in_(sorted(PROFILE_MEMORY_TYPES)),
            UserMemoryORM.is_active.is_(True),
        ).update({"is_active": False}, synchronize_session=False)
        for memory in memories:
            normalized = " ".join(memory.content.strip().split()).lower()
            existing = db.scalar(
                select(UserMemoryORM).where(
                    UserMemoryORM.user_id == user_id,
                    UserMemoryORM.memory_type == memory.memory_type,
                    func.lower(UserMemoryORM.content) == normalized,
                )
            )
            if existing:
                existing.is_active = True
                existing.importance = memory.importance
                existing.updated_at = datetime.utcnow()
            else:
                db.add(UserMemoryORM(
                    user_id=user_id,
                    memory_type=memory.memory_type,
                    content=normalized,
                    importance=memory.importance,
                    is_active=True,
                ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_user_memory(user_id: str | None) -> UserTravelMemory:
    if not user_id:
        return UserTravelMemory()
    db = SessionLocal()
    try:
        items = db.scalars(
            select(UserMemoryORM)
            .where(
                UserMemoryORM.user_id == user_id,
                UserMemoryORM.is_active.is_(True),
            )
            .order_by(UserMemoryORM.importance.desc(), UserMemoryORM.updated_at.desc())
            .limit(50)
        ).all()
        return UserTravelMemory(
            expertise=next((item.content for item in items if item.memory_type == "expertise"), None),
            answer_length=next((item.content for item in items if item.memory_type == "answer_length"), None),
            tone=next((item.content for item in items if item.memory_type == "tone"), None),
            explanation_style=next((item.content for item in items if item.memory_type == "explanation_style"), None),
            interests=[item.content for item in items if item.memory_type == "interest"],
            preferred_travel_styles=[item.content for item in items if item.memory_type == "travel_style"],
            preferred_activities=[item.content for item in items if item.memory_type == "activity"],
            budget_level=next((item.content for item in items if item.memory_type == "budget"), None),
            avoid=[item.content for item in items if item.memory_type in {"avoid", "constraint"}],
            personal_facts=[item.content for item in items if item.memory_type == "personal_fact"],
        )
    finally:
        db.close()
