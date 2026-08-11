from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryLocation(BaseModel):
    country: str | None = None
    city: str | None = None
    province: str | None = None


class QueryConstraints(BaseModel):
    budget: str | None = None
    duration_days: int | None = None

    date_from: str | None = None
    date_to: str | None = None

    near_place: str | None = None
    max_distance_km: float | None = None


class ParsedQuery(BaseModel):
    intent: str | None = None

    location: QueryLocation = Field(
        default_factory=QueryLocation
    )

    place_types: list[str] = Field(
        default_factory=list
    )

    activities: list[str] = Field(
        default_factory=list
    )

    travel_styles: list[str] = Field(
        default_factory=list
    )

    suitable_for: list[str] = Field(
        default_factory=list
    )

    constraints: QueryConstraints = Field(
        default_factory=QueryConstraints
    )


class UserTravelMemory(BaseModel):
    preferred_travel_styles: list[str] = Field(
        default_factory=list
    )
    preferred_activities: list[str] = Field(
        default_factory=list
    )
    budget_level: str | None = None
    avoid: list[str] = Field(
        default_factory=list
    )


class RetrievalConfidence(BaseModel):
    level: str
    score: float
    evidence_count: int
    top_score: float | None = None
    score_gap: float | None = None


class EvidenceItem(BaseModel):
    evidence_id: str
    chunk_id: str
    document_id: str | None = None
    place_name: str | None = None
    content: str
    metadata: dict[str, Any]


class ToolPlan(BaseModel):
    need_weather: bool = False
    need_maps: bool = False
    need_events: bool = False


class ItineraryStop(BaseModel):
    place_name: str
    time_slot: str | None = None
    activity: str | None = None
    reason: str | None = None
    evidence_ids: list[str] = Field(
        default_factory=list
    )


class ItineraryDay(BaseModel):
    day: int
    theme: str | None = None
    stops: list[ItineraryStop] = Field(
        default_factory=list
    )


class StructuredItinerary(BaseModel):
    destination: str | None = None
    days: list[ItineraryDay] = Field(
        default_factory=list
    )
