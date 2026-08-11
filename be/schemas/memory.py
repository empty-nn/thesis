from datetime import datetime

from pydantic import BaseModel


class UserMemoryItem(BaseModel):
    id: int
    memory_type: str
    content: str
    importance: float
    created_at: datetime | None = None
    updated_at: datetime | None = None
