from typing import List, Optional

from pydantic import BaseModel, Field


class TourismMetadata(BaseModel):

    country: Optional[str] = None

    city: Optional[str] = None

    province: Optional[str] = None

    place_name: Optional[str] = None

    place_type: Optional[str] = None

    ai_tags: List[str] = Field(default_factory=list)

    ai_activities: List[str] = Field(default_factory=list)

    ai_travel_styles: List[str] = Field(default_factory=list)

    ai_suitable_for: List[str] = Field(default_factory=list)

    chunk_topic: Optional[str] = None

    summary: Optional[str] = None

    confidence: float = 0.0

    reasoning: Optional[str] = None