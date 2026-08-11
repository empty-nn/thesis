from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import pandas as pd
from langchain_core.documents import Document
from pydantic import BaseModel, Field


BE_ROOT = Path(__file__).resolve().parents[1]
if str(BE_ROOT) not in sys.path:
    sys.path.insert(0, str(BE_ROOT))

from core.model_registry import load_models, unload_models  # noqa: E402
from data_building.extract_metadata.extractor import (  # noqa: E402
    DEEPSEEK_METADATA_MODEL,
    get_deepseek_client,
)
from data_building.extract_metadata.helpers import extract_json_from_text  # noqa: E402
from schemas.pipeline import ParsedQuery, UserTravelMemory  # noqa: E402
from services.answer_pipeline import build_evidence, generate_answer  # noqa: E402
from services.conversation_memory import ConversationState  # noqa: E402
from services.query_processing import parse_query, rewrite_query  # noqa: E402
from services.retrieval import (  # noqa: E402
    bm25_search,
    build_retrieval_filters,
    fuse_results,
    rerank_documents,
    vector_search,
)


@dataclass(frozen=True)
class AblationConfig:
    name: str
    use_rewrite: bool = True
    use_parser: bool = True
    use_vector: bool = True
    use_bm25: bool = True
    use_boosts: bool = True
    use_reranker: bool = True
    use_user_memory: bool = True
    use_conversation_memory: bool = True


CONFIGS = [
    AblationConfig("full"),
    AblationConfig("no_rewrite", use_rewrite=False),
    AblationConfig("vector_only", use_bm25=False),
    AblationConfig("bm25_only", use_vector=False),
    AblationConfig("no_boosts", use_boosts=False),
    AblationConfig("no_reranker", use_reranker=False),
    AblationConfig("no_user_memory", use_user_memory=False),
    AblationConfig("no_conversation_memory", use_conversation_memory=False),
    AblationConfig("no_memory", use_user_memory=False, use_conversation_memory=False),
]


class ChunkJudgment(BaseModel):
    chunk_id: str
    relevance: int = Field(ge=0, le=3)
    reason: str


class ChunkJudgmentBatch(BaseModel):
    judgments: list[ChunkJudgment]


def chunk_id(document: Document) -> str:
    return str(document.metadata.get("chunk_id") or document.metadata.get("id") or "")


def plain_rrf(vector_docs: list[Document], bm25_docs: list[Document], rrf_k: int = 60) -> list[Document]:
    scored: dict[str, tuple[Document, float]] = {}
    for documents, rank_name in ((vector_docs, "vector_rank"), (bm25_docs, "bm25_rank")):
        for rank, document in enumerate(documents, start=1):
            identifier = chunk_id(document)
            current_document, score = scored.get(identifier, (document, 0.0))
            current_document.metadata[rank_name] = rank
            scored[identifier] = (current_document, score + 1 / (rrf_k + rank))
    ranked = sorted(scored.values(), key=lambda item: item[1], reverse=True)
    for document, score in ranked:
        document.metadata["fusion_score"] = score
        document.metadata["metadata_boost"] = 0.0
        document.metadata["geo_boost"] = 0.0
        document.metadata["freshness_boost"] = 0.0
    return [document for document, _ in ranked]


def history_with_state(case: dict, include_state: bool) -> list[dict]:
    history = list(case.get("conversation_history") or [])[-5:]
    state = case.get("conversation_state") if include_state else None
    if state:
        history.append(
            {
                "role": "system",
                "content": "Current conversation trip context: " + json.dumps(state, ensure_ascii=False),
            }
        )
    return history


def execute_configuration(
    case: dict,
    config: AblationConfig,
    generate: bool,
    cache: dict,
) -> dict:
    total_started = perf_counter()
    timings: dict[str, float] = {}
    history = history_with_state(case, config.use_conversation_memory)

    started = perf_counter()
    rewritten = rewrite_query(case["query"], history) if config.use_rewrite else case["query"]
    timings["rewrite_ms"] = (perf_counter() - started) * 1000

    started = perf_counter()
    parse_key = rewritten if config.use_parser else "__no_parser__"
    if parse_key not in cache["parsed"]:
        cache["parsed"][parse_key] = parse_query(rewritten) if config.use_parser else ParsedQuery()
        cache["parse_ms"][parse_key] = (perf_counter() - started) * 1000
    parsed = cache["parsed"][parse_key].model_copy(deep=True)
    timings["parse_ms"] = cache["parse_ms"][parse_key]
    filters = build_retrieval_filters(parsed)

    memory = UserTravelMemory.model_validate(case.get("user_memory") or {}) if config.use_user_memory else UserTravelMemory()
    conversation_state = ConversationState.model_validate(case.get("conversation_state") or {}) if config.use_conversation_memory else ConversationState()

    started = perf_counter()
    retrieval_key = (
        rewritten,
        filters.city,
        filters.province,
        filters.country,
        tuple(filters.place_types),
    )
    if config.use_vector and retrieval_key not in cache["vector"]:
        cache["vector"][retrieval_key] = vector_search(rewritten, filters, limit=30)
        cache["vector_ms"][retrieval_key] = (perf_counter() - started) * 1000
    vector_docs = copy.deepcopy(cache["vector"].get(retrieval_key, [])) if config.use_vector else []
    timings["vector_ms"] = cache["vector_ms"].get(retrieval_key, 0.0) if config.use_vector else 0.0

    started = perf_counter()
    if config.use_bm25 and retrieval_key not in cache["bm25"]:
        cache["bm25"][retrieval_key] = bm25_search(rewritten, filters, limit=30)
        cache["bm25_ms"][retrieval_key] = (perf_counter() - started) * 1000
    bm25_docs = copy.deepcopy(cache["bm25"].get(retrieval_key, [])) if config.use_bm25 else []
    timings["bm25_ms"] = cache["bm25_ms"].get(retrieval_key, 0.0) if config.use_bm25 else 0.0

    started = perf_counter()
    if config.use_boosts:
        hybrid_docs = fuse_results(
            copy.deepcopy(vector_docs),
            copy.deepcopy(bm25_docs),
            parsed,
            memory,
        )
    else:
        hybrid_docs = plain_rrf(copy.deepcopy(vector_docs), copy.deepcopy(bm25_docs))
    candidates = hybrid_docs[:20]
    timings["fusion_ms"] = (perf_counter() - started) * 1000

    started = perf_counter()
    final_docs = rerank_documents(rewritten, copy.deepcopy(candidates), top_k=8) if config.use_reranker else copy.deepcopy(candidates[:8])
    timings["rerank_ms"] = (perf_counter() - started) * 1000

    stages = {
        "vector": vector_docs,
        "bm25": bm25_docs,
        "hybrid": hybrid_docs[:20],
        "final": final_docs,
    }
    answer = None
    if generate:
        started = perf_counter()
        answer = generate_answer(
            query=case["query"],
            rewritten_query=rewritten,
            parsed=parsed,
            evidence=build_evidence(final_docs),
            conversation_history=list(case.get("conversation_history") or []),
            memory=memory,
            conversation_memory=conversation_state,
        )
        timings["generation_ms"] = (perf_counter() - started) * 1000

    timings["wall_clock_ms"] = (perf_counter() - total_started) * 1000
    timings["total_ms"] = sum(
        value
        for key, value in timings.items()
        if key.endswith("_ms") and key not in {"total_ms", "wall_clock_ms"}
    )
    return {
        "case_id": case["id"],
        "configuration": config.name,
        "config": asdict(config),
        "rewritten_query": rewritten,
        "parsed_query": parsed.model_dump(),
        "stages": stages,
        "answer": answer,
        "timings": {key: round(value, 3) for key, value in timings.items()},
        "memory": memory.model_dump(),
        "conversation_state": conversation_state.model_dump(),
    }


def serialize_document(document: Document, rank: int) -> dict:
    return {
        "chunk_id": chunk_id(document),
        "rank": rank,
        "content": document.page_content,
        "metadata": document.metadata,
    }


def serialize_trace(trace: dict) -> dict:
    return {
        **{key: value for key, value in trace.items() if key != "stages"},
        "stages": {
            stage: [serialize_document(document, rank) for rank, document in enumerate(documents, start=1)]
            for stage, documents in trace["stages"].items()
        },
    }


def pool_candidates(traces: list[dict]) -> dict[str, Document]:
    pool: dict[str, Document] = {}
    for trace in traces:
        for documents in trace["stages"].values():
            for document in documents:
                pool.setdefault(chunk_id(document), document)
    return pool


def weak_grade(document: Document, case: dict) -> int:
    text = " ".join(
        [
            document.page_content,
            str(document.metadata.get("place_name") or ""),
            str(document.metadata.get("city") or ""),
            str(document.metadata.get("chunk_topic") or ""),
        ]
    ).lower()
    if any(str(place).lower() in text for place in case.get("expected_places") or []):
        return 3
    if any(str(location).lower() in text for location in case.get("expected_locations") or []):
        return 2
    if any(str(keyword).lower() in text for keyword in case.get("expected_keywords") or []):
        return 1
    return 0


def llm_judge_chunks(case: dict, pool: dict[str, Document], batch_size: int = 8) -> dict[str, dict]:
    client = get_deepseek_client()
    items = list(pool.items())
    judgments: dict[str, dict] = {}
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        chunks = [
            {
                "chunk_id": identifier,
                "place_name": document.metadata.get("place_name"),
                "city": document.metadata.get("city"),
                "content": document.page_content[:1800],
            }
            for identifier, document in batch
        ]
        response = client.chat.completions.create(
            model=DEEPSEEK_METADATA_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": """
Judge each travel chunk's usefulness for answering the query. Do not infer relevance from rank or retrieval scores.
Use: 0 unrelated; 1 related context but not directly useful; 2 useful for part of the query; 3 directly and strongly useful.
Return JSON: {"judgments":[{"chunk_id":"...","relevance":0,"reason":"..."}]}.
Judge every supplied chunk exactly once.
""".strip(),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "query": case["query"],
                            "intent": case.get("intent"),
                            "conversation_history": case.get("conversation_history") or [],
                            "conversation_state": case.get("conversation_state"),
                            "chunks": chunks,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=1200,
        )
        parsed = ChunkJudgmentBatch.model_validate(
            extract_json_from_text(response.choices[0].message.content or "{}")
        )
        for judgment in parsed.judgments:
            judgments[judgment.chunk_id] = judgment.model_dump()
    return judgments


def dcg(grades: list[int], k: int) -> float:
    return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades[:k]))


def stage_metrics(documents: list[Document], judgments: dict[str, dict], k: int = 10) -> dict:
    pool_relevant = {identifier for identifier, judgment in judgments.items() if judgment["relevance"] >= 1}
    grades = [judgments.get(chunk_id(document), {"relevance": 0})["relevance"] for document in documents]
    retrieved_relevant = {chunk_id(document) for document in documents[:k] if chunk_id(document) in pool_relevant}
    recall = len(retrieved_relevant) / len(pool_relevant) if pool_relevant else 0.0
    precision = sum(grade >= 1 for grade in grades[:k]) / k
    ideal = sorted((item["relevance"] for item in judgments.values()), reverse=True)
    ideal_dcg = dcg(ideal, 5)
    ndcg = dcg(grades, 5) / ideal_dcg if ideal_dcg else 0.0
    first = next((index + 1 for index, grade in enumerate(grades) if grade >= 2), None)
    return {
        "pooled_recall_at_10": recall,
        "precision_at_10": precision,
        "ndcg_at_5": ndcg,
        "mrr": 1 / first if first else 0.0,
    }


def judge_answer(case: dict, trace: dict) -> dict:
    from evaluation.run_evaluation import judge_answer as baseline_judge

    scores = baseline_judge(
        case,
        trace["answer"],
        build_evidence(trace["stages"]["final"]),
    )
    return scores.model_dump()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
        encoding="utf-8",
    )


def visualize(frame: pd.DataFrame, all_stages: pd.DataFrame, output_dir: Path) -> None:
    import matplotlib.pyplot as plt

    summary = frame.groupby("configuration").mean(numeric_only=True)
    metrics = ["pooled_recall_at_10", "ndcg_at_5", "mrr"]
    axis = summary[metrics].plot(kind="bar", figsize=(12, 6))
    axis.set_ylim(0, 1)
    axis.set_title("Ablation retrieval quality")
    axis.set_ylabel("Score")
    axis.grid(axis="y", alpha=0.25)
    axis.figure.tight_layout()
    axis.figure.savefig(output_dir / "ablation_retrieval.png", dpi=180)
    plt.close(axis.figure)

    full_stages = all_stages[all_stages["configuration"] == "full"]
    if not full_stages.empty:
        stage_summary = full_stages.groupby("stage").mean(numeric_only=True)
        axis = stage_summary[metrics].plot(kind="bar", figsize=(10, 6))
        axis.set_ylim(0, 1)
        axis.set_title("Full pipeline retrieval quality by stage")
        axis.set_ylabel("Score")
        axis.grid(axis="y", alpha=0.25)
        axis.figure.tight_layout()
        axis.figure.savefig(output_dir / "retrieval_by_stage.png", dpi=180)
        plt.close(axis.figure)

    quality = [column for column in ["answer_relevance", "faithfulness", "citation_correctness", "preference_adherence", "conversation_consistency"] if column in summary]
    if quality:
        axis = summary[quality].plot(kind="bar", figsize=(13, 6))
        axis.set_ylim(0, 3)
        axis.set_title("Ablation final-answer quality")
        axis.set_ylabel("Judge score (0–3)")
        axis.grid(axis="y", alpha=0.25)
        axis.figure.tight_layout()
        axis.figure.savefig(output_dir / "ablation_answer_quality.png", dpi=180)
        plt.close(axis.figure)

    latency = [column for column in ["retrieval_ms", "generation_ms", "total_ms"] if column in summary]
    axis = summary[latency].plot(kind="bar", figsize=(12, 6), color=["#38bdf8", "#10b981", "#f59e0b"][: len(latency)])
    axis.set_title("Ablation latency")
    axis.set_ylabel("Milliseconds")
    axis.grid(axis="y", alpha=0.25)
    axis.figure.tight_layout()
    axis.figure.savefig(output_dir / "ablation_latency.png", dpi=180)
    plt.close(axis.figure)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage-wise and leave-one-component-out RAG evaluation")
    parser.add_argument("--dataset", type=Path, default=Path(__file__).parent / "data" / "travel_rag_benchmark_100.json")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "runs" / "ablation")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--configs", nargs="*", choices=[config.name for config in CONFIGS])
    parser.add_argument("--judge-retrieval", action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--judge-answers", action="store_true")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    if args.judge_answers and not args.generate:
        parser.error("--judge-answers requires --generate")

    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    cases = payload["cases"][: args.limit]
    configs = [config for config in CONFIGS if not args.configs or config.name in args.configs]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    judgment_dir = args.output_dir / "judgments"
    judgment_dir.mkdir(exist_ok=True)

    all_traces: list[dict] = []
    all_judgments: list[dict] = []
    metric_rows: list[dict] = []
    load_models()
    try:
        for case_index, case in enumerate(cases, start=1):
            print(f"[{case_index}/{len(cases)}] {case['id']}", flush=True)
            case_cache = {
                "parsed": {},
                "parse_ms": {},
                "vector": {},
                "vector_ms": {},
                "bm25": {},
                "bm25_ms": {},
            }
            case_traces = [
                execute_configuration(case, config, args.generate, case_cache)
                for config in configs
            ]
            pool = pool_candidates(case_traces)
            cache_path = judgment_dir / f"{case['id']}.json"
            if cache_path.exists():
                judgments = json.loads(cache_path.read_text(encoding="utf-8"))
            elif args.judge_retrieval:
                judgments = llm_judge_chunks(case, pool)
                cache_path.write_text(json.dumps(judgments, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                judgments = {
                    identifier: {
                        "chunk_id": identifier,
                        "relevance": weak_grade(document, case),
                        "reason": "synthetic weak label",
                    }
                    for identifier, document in pool.items()
                }

            all_judgments.extend({"case_id": case["id"], **judgment} for judgment in judgments.values())
            for trace in case_traces:
                all_traces.append(serialize_trace(trace))
                for stage, documents in trace["stages"].items():
                    metric_rows.append(
                        {
                            "case_id": case["id"],
                            "intent": case.get("intent"),
                            "configuration": trace["configuration"],
                            "stage": stage,
                            **stage_metrics(documents, judgments),
                            "retrieval_ms": sum(
                                trace["timings"].get(key, 0)
                                for key in ["rewrite_ms", "parse_ms", "vector_ms", "bm25_ms", "fusion_ms", "rerank_ms"]
                            ),
                            "generation_ms": trace["timings"].get("generation_ms"),
                            "total_ms": trace["timings"]["total_ms"],
                            **(judge_answer(case, trace) if args.judge_answers and stage == "final" else {}),
                        }
                    )
    finally:
        unload_models()

    write_jsonl(args.output_dir / "traces.jsonl", all_traces)
    write_jsonl(args.output_dir / "retrieval_judgments.jsonl", all_judgments)
    frame = pd.DataFrame(metric_rows)
    frame.to_csv(args.output_dir / "stage_case_metrics.csv", index=False, encoding="utf-8-sig")
    final_frame = frame[frame["stage"] == "final"].copy()
    final_frame.to_csv(args.output_dir / "ablation_case_metrics.csv", index=False, encoding="utf-8-sig")
    summary = final_frame.groupby("configuration").mean(numeric_only=True).reset_index()
    summary.to_csv(args.output_dir / "ablation_summary.csv", index=False, encoding="utf-8-sig")
    stage_summary = frame.groupby(["configuration", "stage"]).mean(numeric_only=True).reset_index()
    stage_summary.to_csv(args.output_dir / "stage_summary.csv", index=False, encoding="utf-8-sig")
    contributions = pd.DataFrame()
    if "full" in set(summary["configuration"]):
        full = summary[summary["configuration"] == "full"].iloc[0]
        contribution_rows = []
        for _, row in summary.iterrows():
            if row["configuration"] == "full":
                continue
            contribution = {"configuration": row["configuration"]}
            for column in [
                "pooled_recall_at_10",
                "precision_at_10",
                "ndcg_at_5",
                "mrr",
                "answer_relevance",
                "faithfulness",
                "citation_correctness",
                "preference_adherence",
                "conversation_consistency",
                "total_ms",
            ]:
                if column in summary and pd.notna(full[column]) and pd.notna(row[column]):
                    contribution[f"full_minus_ablation_{column}"] = full[column] - row[column]
            contribution_rows.append(contribution)
        contributions = pd.DataFrame(contribution_rows)
        contributions.to_csv(args.output_dir / "component_contributions.csv", index=False, encoding="utf-8-sig")
    config_payload = {
        "dataset": str(args.dataset),
        "case_count": len(cases),
        "configurations": [asdict(config) for config in configs],
        "retrieval_judge": "llm" if args.judge_retrieval else "synthetic_weak_label",
        "generate_answers": args.generate,
        "judge_answers": args.judge_answers,
    }
    (args.output_dir / "configuration.json").write_text(json.dumps(config_payload, indent=2), encoding="utf-8")
    report_lines = [
        "# Ablation Evaluation Report",
        "",
        f"- Dataset: `{args.dataset}`",
        f"- Cases: {len(cases)}",
        f"- Retrieval judgments: {config_payload['retrieval_judge']}",
        f"- Answer generation: {args.generate}",
        f"- Answer judging: {args.judge_answers}",
        "",
        "## Final-stage ablation summary",
        "",
        summary.to_markdown(index=False),
        "",
        "## Retrieval stage summary",
        "",
        stage_summary.to_markdown(index=False),
    ]
    if not contributions.empty:
        report_lines.extend(
            [
                "",
                "## Component contribution relative to full system",
                "",
                "Positive quality values mean the full system performed better. Positive total-latency values represent the component's latency cost.",
                "",
                contributions.to_markdown(index=False),
            ]
        )
    (args.output_dir / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    if not args.no_plots:
        visualize(final_frame, frame, args.output_dir)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
