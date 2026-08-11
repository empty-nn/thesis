from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PreferenceConstraint(BaseModel):
    key: str
    value: str


class ReferenceLabels(BaseModel):
    intent: str
    operation: str = "lookup"
    query_constraints: list[PreferenceConstraint] = Field(default_factory=list)
    applicable_personalization: list[PreferenceConstraint] = Field(default_factory=list)
    relevant_memory_ids: list[str] = Field(default_factory=list)
    relevance_grades: dict[str, int] = Field(default_factory=dict)
    key_answer_facts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relevance_grades(self) -> "ReferenceLabels":
        invalid = {
            chunk_id: grade
            for chunk_id, grade in self.relevance_grades.items()
            if grade not in {0, 1, 2, 3}
        }
        if invalid:
            raise ValueError(f"Relevance grades must be integers from 0 to 3: {invalid}")
        return self


class UnderstandingPrediction(BaseModel):
    intent: str
    operation: str = "lookup"
    query_constraints: list[PreferenceConstraint] = Field(default_factory=list)


class RetrievalPrediction(BaseModel):
    retrieved_chunk_ids: list[str]
    selected_evidence_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict)


class FinalAnswerScores(BaseModel):
    correctness: float = Field(ge=1, le=5)
    faithfulness: float = Field(ge=1, le=5)
    personalization_adherence: float = Field(ge=1, le=5)
    completeness: float = Field(ge=1, le=5)
    rationale: dict[str, str] = Field(default_factory=dict)
    judge_model: str | None = None


class Prediction(BaseModel):
    understanding: UnderstandingPrediction
    retrieval: RetrievalPrediction
    final_answer: str
    final_answer_scores: FinalAnswerScores | None = None


class ThesisEvaluationCase(BaseModel):
    case_id: str
    user_id: str
    conversation_id: str
    turn_id: int = Field(ge=1)
    query: str
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    user_profile: dict = Field(default_factory=dict)
    user_memories: list[dict] = Field(default_factory=list)
    annotation_status: Literal["synthetic_weak_label", "llm_annotated", "human_annotated"]
    reference: ReferenceLabels
    prediction: Prediction


class ThesisDataset(BaseModel):
    version: str = "1.2"
    cases: list[ThesisEvaluationCase]
