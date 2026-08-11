from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select

from data_building.extract_metadata.extractor import (
    DEEPSEEK_METADATA_MODEL,
    get_deepseek_client,
)
from services.llm_telemetry import create_chat_completion
from data_building.extract_metadata.helpers import extract_json_from_text
from db.full_model import ConversationORM
from db.session import SessionLocal


class ConversationState(BaseModel):
    summary: str = ""
    destination: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    original_date_text: str | None = None
    duration_days: int | None = Field(default=None, ge=1)
    temporary_budget: str | None = None
    selected_places: list[str] = Field(default_factory=list)
    trip_constraints: list[str] = Field(default_factory=list)

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def normalize_date_range(self) -> "ConversationState":
        start = date.fromisoformat(self.date_from) if self.date_from else None
        end = date.fromisoformat(self.date_to) if self.date_to else None

        if start and not end and self.duration_days:
            end = start + timedelta(days=self.duration_days - 1)
            self.date_to = end.isoformat()
        elif end and not start and self.duration_days:
            start = end - timedelta(days=self.duration_days - 1)
            self.date_from = start.isoformat()

        if start and end:
            if end < start:
                raise ValueError("date_to must not be before date_from")
            self.duration_days = (end - start).days + 1

        self.selected_places = list(dict.fromkeys(self.selected_places))
        self.trip_constraints = list(dict.fromkeys(self.trip_constraints))

        return self


def get_conversation_memory(
    user_id: str | None,
    conversation_id: str | None,
) -> ConversationState:
    if not user_id or not conversation_id:
        return ConversationState()
    db = SessionLocal()
    try:
        conversation = db.scalar(
            select(ConversationORM).where(
                ConversationORM.id == conversation_id,
                ConversationORM.user_id == user_id,
            )
        )
        if not conversation:
            return ConversationState()
        state = conversation.conversation_state or {}
        if conversation.summary and not state.get("summary"):
            state = {**state, "summary": conversation.summary}
        return ConversationState.model_validate(state)
    finally:
        db.close()


def update_conversation_memory(
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    try:
        previous = get_conversation_memory(user_id, conversation_id)
        state = derive_conversation_state(
            previous=previous,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        db = SessionLocal()
        try:
            conversation = db.scalar(
                select(ConversationORM).where(
                    ConversationORM.id == conversation_id,
                    ConversationORM.user_id == user_id,
                )
            )
            if not conversation:
                return
            conversation.summary = state.summary
            conversation.conversation_state = state.model_dump()
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        print(f"[CONVERSATION MEMORY UPDATE FAILED] {exc}")


def derive_conversation_state(
    previous: ConversationState,
    user_message: str,
    assistant_message: str,
    current_date: date | None = None,
    timezone_name: str | None = None,
) -> ConversationState:
    timezone_name = timezone_name or os.getenv("USER_TIMEZONE", "Asia/Ho_Chi_Minh")
    current_date = current_date or datetime.now(ZoneInfo(timezone_name)).date()
    client = get_deepseek_client()
    response = create_chat_completion(
            "conversation_state", client,
            model=DEEPSEEK_METADATA_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": """
Maintain structured temporary state for one travel conversation.
Return one JSON object matching the supplied schema and containing the complete updated state.

Rules:
- Preserve still-relevant facts from the previous state.
- Record only facts explicit in this conversation.
- This state is trip-specific, not a permanent user profile.
- Track only destination, dates, duration, temporary budget, selected places, and trip constraints.
- Keep date_from and date_to in YYYY-MM-DD format.
- Preserve the user's exact date phrase in original_date_text.
- Resolve relative dates such as "next weekend" against the supplied current date and timezone.
- For one exact visit date, set date_from and date_to to the same date.
- If a start date and duration are given, derive the inclusive end date.
- Never guess a date that cannot be resolved from the message and supplied current date.
- Replace old trip dates when the user explicitly changes them.
- Keep lists concise and deduplicated.
- Keep summary under 180 words.
- Do not store credentials, contact details, payment data, or sensitive personal information.
""".strip(),
                },
                {
                    "role": "user",
                    "content": f"""
Previous state:
{json.dumps(previous.model_dump(), ensure_ascii=False, indent=2)}

Current date: {current_date.isoformat()}
User timezone: {timezone_name}

Latest user message:
{user_message}

Latest assistant answer:
{assistant_message}

Return the complete updated state as JSON.
""".strip(),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=800,
        )
    content = response.choices[0].message.content
    if not content:
        return previous
    return ConversationState.model_validate(extract_json_from_text(content))
