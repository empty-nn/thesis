from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class QueryLocation(BaseModel):
    country: str | None = None
    region: str | None = None
    city: str | None = None
    cities: list[str] = Field(default_factory=list)
    province: str | None = None

    @model_validator(mode="after")
    def normalize_cities(self) -> "QueryLocation":
        values = [value for value in [self.city, *self.cities] if value]
        self.cities = list(dict.fromkeys(values))
        self.city = self.cities[0] if self.cities else None
        return self


class QueryConstraints(BaseModel):
    budget: str | None = None
    duration_days: int | None = None

    date_from: str | None = None
    date_to: str | None = None

    near_place: str | None = None
    max_distance_km: float | None = None


class ExplicitConstraint(BaseModel):
    key: str
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def stringify_value(cls, value: Any) -> str:
        if value is None:
            raise ValueError("Explicit constraint value cannot be null")
        return str(value)


class ParsedQuery(BaseModel):
    intent: str | None = None
    operation: str | None = None
    raw_intent: str | None = None
    raw_operation: str | None = None
    intent_was_invalid: bool = False
    operation_was_invalid: bool = False
    parser_used_fallback: bool = False

    explicit_constraints: list[ExplicitConstraint] = Field(
        default_factory=list
    )

    @field_validator("explicit_constraints", mode="before")
    @classmethod
    def normalize_explicit_constraint_shape(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, dict):
            value = (
                [value]
                if "key" in value and "value" in value
                else [
                    {"key": key, "value": item_value}
                    for key, item_value in value.items()
                ]
            )
        if not isinstance(value, list):
            raise ValueError("explicit_constraints must be a list")
        normalized: list[Any] = []
        for item in value:
            if (
                isinstance(item, dict)
                and "key" not in item
                and "value" not in item
                and len(item) == 1
            ):
                key, item_value = next(iter(item.items()))
                normalized.append({"key": key, "value": item_value})
            else:
                normalized.append(item)
        return normalized

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
    expertise: str | None = None
    answer_length: str | None = None
    tone: str | None = None
    explanation_style: str | None = None
    interests: list[str] = Field(
        default_factory=list
    )
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
    personal_facts: list[str] = Field(
        default_factory=list
    )


class RetrievalConfidence(BaseModel):
    level: str
    score: float
    evidence_count: int
    top_score: float | None = None
    score_gap: float | None = None


class RetrievalTask(BaseModel):
    task_type: str = "general"
    query: str
    top_k: int = Field(default=10, ge=1, le=20)
    cities: list[str] = Field(default_factory=list)
    requirement_indexes: list[int] = Field(default_factory=list)


class AgenticRetrievalPlan(BaseModel):
    complexity: str = "simple"
    requirements: list[str] = Field(default_factory=list)
    retrieval_tasks: list[RetrievalTask] = Field(default_factory=list)
    used_fallback: bool = False


class RequirementCoverage(BaseModel):
    requirement: str
    status: Literal["covered", "partially_covered", "not_covered"]
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    additional_query: str | None = None


class EvidenceCoverage(BaseModel):
    sufficient: bool = True
    coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    requirement_count: int = Field(default=0, ge=0)
    covered_count: int = Field(default=0, ge=0)
    partial_count: int = Field(default=0, ge=0)
    missing_count: int = Field(default=0, ge=0)
    requirement_assessments: list[RequirementCoverage] = Field(default_factory=list)
    covered_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    additional_queries: list[str] = Field(default_factory=list)
    used_fallback: bool = False

    @model_validator(mode="after")
    def calculate_aggregates(self) -> "EvidenceCoverage":
        if not self.requirement_assessments:
            return self
        self.requirement_count = len(self.requirement_assessments)
        self.covered_requirements = [
            item.requirement
            for item in self.requirement_assessments
            if item.status == "covered"
        ]
        self.missing_requirements = [
            item.requirement
            for item in self.requirement_assessments
            if item.status != "covered"
        ]
        self.covered_count = len(self.covered_requirements)
        self.partial_count = sum(
            item.status == "partially_covered"
            for item in self.requirement_assessments
        )
        self.missing_count = self.requirement_count - self.covered_count
        # Partial evidence is useful for a guarded partial answer and recovery,
        # but never makes the overall result sufficient.
        self.coverage_ratio = (
            self.covered_count + 0.5 * self.partial_count
        ) / self.requirement_count
        self.sufficient = self.missing_count == 0
        return self


class AnswerReadiness(BaseModel):
    mode: Literal["complete", "partial", "insufficient"]
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    duration_days: int | None = None
    distinct_supported_place_count: int = Field(ge=0)
    minimum_required_place_count: int = Field(ge=0)
    reason: str


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
