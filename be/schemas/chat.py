from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_history: list[ConversationMessage] = Field(
        default_factory=list
    )
    user_id: str | None = None
    conversation_id: str | None = None


class ChatSource(BaseModel):
    id: str
    title: str
    url: str | None = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str | None = None
    sources: list[ChatSource] = Field(
        default_factory=list
    )
    knowledge_gap: dict | None = Field(default=None, exclude=True)
    route_category: str = Field(default="travel", exclude=True)


class ConversationSummary(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SavedMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime | None = None


class ConversationDetail(BaseModel):
    id: str
    title: str | None = None
    messages: list[SavedMessage] = Field(default_factory=list)
