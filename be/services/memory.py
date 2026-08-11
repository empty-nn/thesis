from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from data_building.extract_metadata.extractor import (
    DEEPSEEK_METADATA_MODEL,
    get_deepseek_client,
)
from data_building.extract_metadata.helpers import extract_json_from_text
from db.full_model import UserMemoryORM
from db.session import SessionLocal
from schemas.pipeline import UserTravelMemory


MemoryType = Literal[
    "travel_style",
    "activity",
    "budget",
    "avoid",
    "constraint",
]


class ExtractedMemory(BaseModel):
    memory_type: MemoryType
    content: str = Field(min_length=1, max_length=200)
    importance: float = Field(default=0.7, ge=0, le=1)


class MemoryExtraction(BaseModel):
    memories: list[ExtractedMemory] = Field(default_factory=list)


def extract_memories(message: str) -> list[ExtractedMemory]:
    client = get_deepseek_client()
    response = client.chat.completions.create(
        model=DEEPSEEK_METADATA_MODEL,
        messages=[
            {
                "role": "system",
                "content": """
You extract explicit, durable travel preferences for personalization.

Return JSON only in this shape:
{"memories":[{"memory_type":"travel_style|activity|budget|avoid|constraint","content":"short normalized value","importance":0.0}]}

Save only information the user explicitly states about themselves that is likely useful in future trips.
Examples: preferred travel style, favorite activity, usual budget, things they avoid, durable accessibility or dietary travel constraints.

Do not save:
- the current destination, dates, itinerary, or one-time request
- facts merely mentioned in a question
- guesses or inferred preferences
- names, email, address, credentials, identifiers, or payment data
- medical details, religion, politics, sexuality, ethnicity, or other sensitive personal data
- anything said by the assistant

Use an empty memories list when there is no safe durable preference.
Keep content concise and standalone. Use lowercase snake_case for simple labels when possible.
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
    return MemoryExtraction.model_validate(parsed).memories


def save_memories(user_id: str, memories: list[ExtractedMemory]) -> None:
    if not memories:
        return
    db = SessionLocal()
    try:
        for memory in memories:
            normalized = " ".join(memory.content.strip().split()).lower()
            if not normalized:
                continue
            if memory.memory_type == "budget":
                db.query(UserMemoryORM).filter(
                    UserMemoryORM.user_id == user_id,
                    UserMemoryORM.memory_type == "budget",
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
            preferred_travel_styles=[item.content for item in items if item.memory_type == "travel_style"],
            preferred_activities=[item.content for item in items if item.memory_type == "activity"],
            budget_level=next((item.content for item in items if item.memory_type == "budget"), None),
            avoid=[item.content for item in items if item.memory_type in {"avoid", "constraint"}],
        )
    finally:
        db.close()
