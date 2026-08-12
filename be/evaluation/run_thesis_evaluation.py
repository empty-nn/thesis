from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from statistics import mean

import httpx
import pandas as pd
from dotenv import load_dotenv

try:
    from .thesis_evaluation_schema import FinalAnswerScores, ThesisDataset, ThesisEvaluationCase
except ImportError:  # Direct script execution from the evaluation directory.
    from thesis_evaluation_schema import FinalAnswerScores, ThesisDataset, ThesisEvaluationCase


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


METRICS = [
    "intent_accuracy",
    "operation_accuracy",
    "query_constraint_f1",
    "retrieval_facet_f1",
    "ndcg_at_5",
    "precision_at_5",
    "correctness",
    "faithfulness",
    "personalization_adherence",
    "completeness",
]


def canonical(value: object) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def f1(actual: set[tuple[str, str]], expected: set[tuple[str, str]]) -> float:
    if not actual and not expected:
        return 1.0
    overlap = len(actual & expected)
    precision = overlap / len(actual) if actual else 0.0
    recall = overlap / len(expected) if expected else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def dcg(grades: list[int], k: int = 5) -> float:
    return sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades[:k]))


def deterministic_metrics(case: ThesisEvaluationCase) -> dict[str, float]:
    reference = case.reference
    prediction = case.prediction
    expected_constraints = {(canonical(item.key), canonical(item.value)) for item in reference.query_constraints}
    actual_constraints = {
        (canonical(item.key), canonical(item.value))
        for item in prediction.understanding.query_constraints
    }
    expected_facets = {
        (canonical(item.key), canonical(item.value))
        for item in reference.retrieval_facets
    }
    actual_facets = {
        (canonical(item.key), canonical(item.value))
        for item in prediction.understanding.retrieval_facets
    }
    top_five = prediction.retrieval.retrieved_chunk_ids[:5]
    grades = [reference.relevance_grades.get(chunk_id, 0) for chunk_id in top_five]
    ideal_grades = sorted(reference.relevance_grades.values(), reverse=True)
    ideal_dcg = dcg(ideal_grades)
    return {
        "intent_accuracy": float(canonical(prediction.understanding.intent) == canonical(reference.intent)),
        "operation_accuracy": float(
            canonical(prediction.understanding.operation) == canonical(reference.operation)
        ),
        "query_constraint_f1": f1(actual_constraints, expected_constraints),
        "retrieval_facet_f1": f1(actual_facets, expected_facets),
        "ndcg_at_5": dcg(grades) / ideal_dcg if ideal_dcg else 0.0,
        "precision_at_5": sum(grade >= 2 for grade in grades) / 5,
    }


JUDGE_RUBRIC = """
You are an independent evaluator. Judge only the supplied answer, evidence, reference facts,
user preferences, query, and conversation. Do not reward writing style unless it helps satisfy
the request. Score each dimension from 1 to 5:
1 = seriously incorrect or unsatisfied; 2 = major problems; 3 = partially correct;
4 = correct with minor omissions; 5 = fully correct.

Correctness: factual accuracy against the reference facts and evidence.
Faithfulness: every externally verifiable claim is supported by supplied evidence; unsupported
claims lower the score.
Personalization adherence: correctly applies relevant user profile, stable memory, preferences,
conversation context, and temporary trip constraints without applying irrelevant information.
Completeness: answers all important parts of the request.
If evidence is insufficient, an answer that clearly states the limitation may remain faithful
and correct, but completeness should be lower. If it invents missing information, lower
faithfulness and correctness as well.

Return one JSON object only with correctness, faithfulness, personalization_adherence, completeness,
and rationale. Rationale must contain a short explanation for each of the four dimensions.
""".strip()


def judge_payload(case: ThesisEvaluationCase) -> dict:
    retrieval = case.prediction.retrieval
    return {
        "query": case.query,
        "conversation_history": case.conversation_history,
        "user_profile": case.user_profile,
        "relevant_user_memories": [
            memory
            for memory in case.user_memories
            if memory.get("memory_id") in set(case.reference.relevant_memory_ids)
        ],
        "expected_intent": case.reference.intent,
        "expected_operation": case.reference.operation,
        "expected_query_constraints": [item.model_dump() for item in case.reference.query_constraints],
        "applicable_personalization": [item.model_dump() for item in case.reference.applicable_personalization],
        "relevant_memory_ids": case.reference.relevant_memory_ids,
        "reference_facts": case.reference.key_answer_facts,
        "evidence": [
            {"chunk_id": chunk_id, "text": retrieval.evidence.get(chunk_id, "")}
            for chunk_id in retrieval.selected_evidence_ids
        ],
        "answer": case.prediction.final_answer,
    }


def extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Judge response did not contain a JSON object")
    return json.loads(cleaned[start : end + 1])


def call_judge(case: ThesisEvaluationCase, provider: str) -> FinalAnswerScores:
    api_key = os.environ.get("JUDGE_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("JUDGE_MODEL", "gpt-5.6-terra")
    if not api_key or not model:
        raise RuntimeError("Set OPENAI_API_KEY (or JUDGE_API_KEY) before using --judge")
    payload_text = json.dumps(judge_payload(case), ensure_ascii=False)
    timeout = float(os.environ.get("JUDGE_TIMEOUT_SECONDS", "90"))
    if provider == "anthropic":
        base_url = os.environ.get("JUDGE_BASE_URL", "https://api.anthropic.com")
        response = httpx.post(
            f"{base_url.rstrip('/')}/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": model,
                "max_tokens": 700,
                "temperature": 0,
                "system": JUDGE_RUBRIC,
                "messages": [{"role": "user", "content": payload_text}],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        content = "".join(item.get("text", "") for item in response.json().get("content", []))
    else:
        base_url = os.environ.get("JUDGE_BASE_URL", "https://api.openai.com/v1")
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": JUDGE_RUBRIC},
                    {"role": "user", "content": payload_text},
                ],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    scores = FinalAnswerScores.model_validate(extract_json(content))
    scores.judge_model = model
    return scores


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the nine primary thesis metrics")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "runs" / "thesis_metrics")
    parser.add_argument("--judge", action="store_true", help="Call the configured independent LLM judge")
    parser.add_argument(
        "--judge-provider",
        choices=["openai", "openai-compatible", "anthropic"],
        default=os.environ.get("JUDGE_PROVIDER", "openai"),
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    dataset = ThesisDataset.model_validate_json(args.dataset.read_text(encoding="utf-8"))
    cases = dataset.cases[: args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    judge_packets: list[dict] = []
    for case in cases:
        scores = case.prediction.final_answer_scores
        if args.judge:
            scores = call_judge(case, args.judge_provider)
        row = {
            "case_id": case.case_id,
            "user_id": case.user_id,
            "conversation_id": case.conversation_id,
            "turn_id": case.turn_id,
            "annotation_status": case.annotation_status,
            **deterministic_metrics(case),
        }
        if scores:
            row.update(scores.model_dump(exclude={"rationale", "judge_model"}))
            row["judge_model"] = scores.judge_model
            row["judge_rationale"] = json.dumps(scores.rationale, ensure_ascii=False)
        rows.append(row)
        judge_packets.append({"case_id": case.case_id, "rubric": JUDGE_RUBRIC, "input": judge_payload(case)})

    pd.DataFrame(rows).to_csv(args.output_dir / "case_metrics.csv", index=False, encoding="utf-8-sig")
    (args.output_dir / "case_metrics.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "judge_packets.json").write_text(json.dumps(judge_packets, ensure_ascii=False, indent=2), encoding="utf-8")
    human_review_rows = [
        {
            "case_id": case.case_id,
            "query": case.query,
            "answer": case.prediction.final_answer,
            "human_correctness": "",
            "human_faithfulness": "",
            "human_personalization_adherence": "",
            "human_completeness": "",
            "reviewer_notes": "",
        }
        for case in cases
    ]
    pd.DataFrame(human_review_rows).to_csv(
        args.output_dir / "human_review_template.csv", index=False, encoding="utf-8-sig"
    )
    available = {metric: [row[metric] for row in rows if metric in row] for metric in METRICS}
    summary = {
        "dataset": str(args.dataset),
        "case_count": len(cases),
        "metric_means": {metric: mean(values) if values else None for metric, values in available.items()},
        "warning": "Only human_annotated cases should be treated as final ground-truth results.",
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
