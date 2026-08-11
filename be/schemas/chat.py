from __future__ import annotations

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
