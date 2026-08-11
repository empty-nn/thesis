from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import mean
from time import perf_counter

import pandas as pd
from pydantic import BaseModel, Field


BE_ROOT = Path(__file__).resolve().parents[1]
if str(BE_ROOT) not in sys.path:
    sys.path.insert(0, str(BE_ROOT))

from data_building.extract_metadata.extractor import (  # noqa: E402
    DEEPSEEK_METADATA_MODEL,
    get_deepseek_client,
)
from data_building.extract_metadata.helpers import extract_json_from_text  # noqa: E402
from schemas.pipeline import UserTravelMemory  # noqa: E402
from core.model_registry import load_models, unload_models  # noqa: E402
from services.answer_pipeline import build_evidence, generate_answer  # noqa: E402
from services.conversation_memory import ConversationState  # noqa: E402
from services.pipeline_runner import run_retrieval_pipeline  # noqa: E402


class JudgeScores(BaseModel):
    answer_relevance: float = Field(ge=0, le=3)
    faithfulness: float = Field(ge=0, le=3)
    citation_correctness: float = Field(ge=0, le=3)
    preference_adherence: float | None = Field(default=None, ge=0, le=3)
    conversation_consistency: float | None = Field(default=None, ge=0, le=3)


def normalize(value: object) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def document_text(document) -> str:
    metadata = document.metadata
    values = [
        document.page_content,
        metadata.get("city"),
        metadata.get("province"),
        metadata.get("place_name"),
        metadata.get("ai_topic"),
        " ".join(metadata.get("ai_tags") or []),
        " ".join(metadata.get("ai_activities") or []),
    ]
    return normalize(" ".join(str(value or "") for value in values))


def weak_relevance_grade(document, case: dict) -> int:
    text = document_text(document)
    place_hits = sum(normalize(item) in text for item in case["expected_places"])
    location_hits = sum(normalize(item) in text for item in case["expected_locations"])
    keyword_hits = sum(normalize(item) in text for item in case["expected_keywords"])
    if place_hits:
        return 3
    if location_hits and keyword_hits:
        return 2
    if location_hits or keyword_hits >= 2:
        return 1
    return 0


def qrel_grade(document, case: dict) -> int:
    qrels = set(case.get("relevant_chunk_ids") or [])
    if not qrels:
        return weak_relevance_grade(document, case)
    chunk_id = str(document.metadata.get("chunk_id") or document.metadata.get("id") or "")
    return 3 if chunk_id in qrels else 0


def dcg(grades: list[int], k: int) -> float:
    return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades[:k]))


def retrieval_metrics(documents: list, case: dict, k: int = 10) -> dict[str, float]:
    grades = [qrel_grade(document, case) for document in documents]
    relevant = [grade > 0 for grade in grades]
    precision = sum(relevant[:k]) / k
    first_rank = next((index + 1 for index, value in enumerate(relevant) if value), None)
    mrr = 1 / first_rank if first_rank else 0.0
    qrels = set(case.get("relevant_chunk_ids") or [])
    ideal_relevant_count = len(qrels) if qrels else len(case["expected_places"])
    ideal = [3] * ideal_relevant_count
    ideal_dcg = dcg(ideal, min(5, k))
    ndcg = dcg(grades, min(5, k)) / ideal_dcg if ideal_dcg else 0.0

    if qrels:
        retrieved_ids = {
            str(document.metadata.get("chunk_id") or document.metadata.get("id") or "")
            for document in documents[:k]
        }
        recall = len(qrels & retrieved_ids) / len(qrels)
    else:
        expected = [normalize(item) for item in case["expected_places"]]
        top_text = " ".join(document_text(document) for document in documents[:k])
        recall = sum(item in top_text for item in expected) / len(expected) if expected else 0.0

    return {
        f"recall_at_{k}": recall,
        f"precision_at_{k}": precision,
        "ndcg_at_5": ndcg,
        "mrr": mrr,
    }


def judge_answer(case: dict, answer: str, evidence: list) -> JudgeScores:
    evidence_text = "\n\n".join(
        f"[{item.evidence_id}] {item.content}" for item in evidence
    )
    client = get_deepseek_client()
    response = client.chat.completions.create(
        model=DEEPSEEK_METADATA_MODEL,
        messages=[
            {
                "role": "system",
                "content": """
You are an impartial evaluator of a travel RAG answer. Score each applicable dimension from 0 to 3.
Answer relevance: directly and completely answers the query.
Faithfulness: factual claims are supported by supplied evidence.
Citation correctness: inline evidence IDs support associated claims.
Preference adherence: relevant supplied user memory is applied without invention.
Conversation consistency: relevant supplied trip state is respected.
Use null for the last two dimensions when their context is absent. Return JSON only.
""".strip(),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "query": case["query"],
                        "expected_locations": case["expected_locations"],
                        "expected_places": case["expected_places"],
                        "user_memory": case.get("user_memory"),
                        "conversation_state": case.get("conversation_state"),
                        "answer": answer,
                        "evidence": evidence_text,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=300,
    )
    return JudgeScores.model_validate(
        extract_json_from_text(response.choices[0].message.content or "{}")
    )


def evaluate_case(case: dict, generate: bool, judge: bool) -> dict:
    started = perf_counter()
    artifacts = run_retrieval_pipeline(
        query=case["query"],
        conversation_history=[],
        user_id=None,
    )
    evidence = build_evidence(artifacts.reranked_docs)
    result = {
        "id": case["id"],
        "query": case["query"],
        "intent": case["intent"],
        "annotation_status": case["annotation_status"],
        **retrieval_metrics(artifacts.reranked_docs, case),
        "rewrite_ms": artifacts.timings.rewrite_ms,
        "vector_ms": artifacts.timings.vector_ms,
        "bm25_ms": artifacts.timings.bm25_ms,
        "hybrid_ms": artifacts.timings.hybrid_ms,
        "rerank_ms": artifacts.timings.rerank_ms,
        "retrieval_total_ms": artifacts.timings.total_ms,
    }

    if generate:
        user_memory = UserTravelMemory.model_validate(case.get("user_memory") or {})
        conversation_state = ConversationState.model_validate(case.get("conversation_state") or {})
        generation_started = perf_counter()
        answer = generate_answer(
            query=case["query"],
            rewritten_query=artifacts.rewritten_query,
            parsed=artifacts.parsed,
            evidence=evidence,
            conversation_history=[],
            memory=user_memory,
            conversation_memory=conversation_state,
        )
        result["answer"] = answer
        result["generation_ms"] = round((perf_counter() - generation_started) * 1000, 3)
        result["citation_count"] = sum(answer.count(f"[{item.evidence_id}]") for item in evidence)
        if judge:
            result.update(judge_answer(case, answer, evidence).model_dump())

    result["evaluation_total_ms"] = round((perf_counter() - started) * 1000, 3)
    return result


def create_visualizations(frame: pd.DataFrame, output_dir: Path) -> None:
    import matplotlib.pyplot as plt

    metric_columns = [column for column in ["recall_at_10", "precision_at_10", "ndcg_at_5", "mrr"] if column in frame]
    means = frame[metric_columns].mean()
    fig, axis = plt.subplots(figsize=(8, 5))
    means.plot(kind="bar", ax=axis, color="#10b981")
    axis.set_ylim(0, 1)
    axis.set_title("Mean retrieval metrics")
    axis.set_ylabel("Score")
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "retrieval_metrics.png", dpi=180)
    plt.close(fig)

    latency_columns = [column for column in ["rewrite_ms", "vector_ms", "bm25_ms", "hybrid_ms", "rerank_ms", "generation_ms"] if column in frame]
    fig, axis = plt.subplots(figsize=(9, 5))
    frame[latency_columns].mean().plot(kind="bar", ax=axis, color="#38bdf8")
    axis.set_title("Mean pipeline latency by stage")
    axis.set_ylabel("Milliseconds")
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "latency_by_stage.png", dpi=180)
    plt.close(fig)

    by_intent = frame.groupby("intent")["recall_at_10"].mean().sort_values()
    fig, axis = plt.subplots(figsize=(9, 5))
    by_intent.plot(kind="barh", ax=axis, color="#f59e0b")
    axis.set_xlim(0, 1)
    axis.set_title("Recall@10 by intent")
    axis.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "recall_by_intent.png", dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless Travel RAG evaluator")
    parser.add_argument("--dataset", type=Path, default=Path(__file__).parent / "data" / "travel_rag_benchmark_100.json")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "results")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--generate", action="store_true", help="Generate final answers with DeepSeek")
    parser.add_argument("--judge", action="store_true", help="Use DeepSeek to score generated answers")
    parser.add_argument("--no-plots", action="store_true", help="Skip PNG visualization generation")
    args = parser.parse_args()
    if args.judge and not args.generate:
        parser.error("--judge requires --generate")

    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    cases = payload["cases"][: args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    load_models()
    try:
        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case['id']}: {case['query']}", flush=True)
            try:
                rows.append(evaluate_case(case, args.generate, args.judge))
            except Exception as exc:
                rows.append({"id": case["id"], "query": case["query"], "intent": case["intent"], "error": str(exc)})
    finally:
        unload_models()

    frame = pd.DataFrame(rows)
    frame.to_csv(args.output_dir / "case_results.csv", index=False, encoding="utf-8-sig")
    (args.output_dir / "case_results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    successful = frame[frame["error"].isna()] if "error" in frame else frame
    summary = {
        "dataset": str(args.dataset),
        "case_count": len(frame),
        "successful_count": len(successful),
        "failed_count": len(frame) - len(successful),
        "annotation_warning": "Cases marked synthetic_weak_label are not human ground truth.",
        "means": {column: float(successful[column].dropna().mean()) for column in successful.select_dtypes(include="number").columns},
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if not successful.empty and not args.no_plots:
        create_visualizations(successful, args.output_dir)
    print(json.dumps(summary, indent=2))
    if successful.empty:
        raise SystemExit("No evaluation cases completed successfully")


if __name__ == "__main__":
    main()
