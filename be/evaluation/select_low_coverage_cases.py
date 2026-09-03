from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FINAL_METRICS = (
    "correctness",
    "faithfulness",
    "personalization_adherence",
    "completeness",
)


def _coverage(case: dict[str, Any]) -> dict[str, Any]:
    retrieval = case.get("retrieval") or {}
    return (
        retrieval.get("coverage_after_recovery")
        or retrieval.get("coverage_check")
        or {}
    )


def _mean(rows: list[dict[str, Any]], getter) -> float:
    values = [float(getter(row)) for row in rows]
    return sum(values) / len(values) if values else 0.0


def _pearson(rows: list[dict[str, Any]], metric: str) -> float | None:
    pairs = []
    for row in rows:
        score = (row.get("final_answer_scores") or {}).get(metric)
        if score is not None:
            pairs.append((float(_coverage(row).get("coverage_ratio", 0)), float(score)))
    if len(pairs) < 2:
        return None
    mean_x = sum(item[0] for item in pairs) / len(pairs)
    mean_y = sum(item[1] for item in pairs) / len(pairs)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x, _ in pairs)
        * sum((y - mean_y) ** 2 for _, y in pairs)
    )
    return numerator / denominator if denominator else None


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, float]:
    result = {
        "coverage_after_recovery": _mean(
            rows, lambda row: _coverage(row).get("coverage_ratio", 0)
        )
    }
    for metric in FINAL_METRICS:
        result[metric] = _mean(
            rows, lambda row, name=metric: (row.get("final_answer_scores") or {})[name]
        )
    return {key: round(value, 4) for key, value in result.items()}


def select_cases(source: dict[str, Any], count: int) -> dict[str, Any]:
    cases = list(source.get("cases") or [])
    if not cases:
        raise ValueError("The source run contains no cases")
    count = min(max(1, count), len(cases))
    ranked = sorted(
        cases,
        key=lambda case: (
            float(_coverage(case).get("coverage_ratio", 0)),
            -int(_coverage(case).get("missing_count", 0)),
            str(case.get("case_id") or ""),
        ),
    )
    selected = ranked[:count]
    remaining = ranked[count:]

    compact_cases = []
    for rank, case in enumerate(selected, start=1):
        coverage = _coverage(case)
        compact_cases.append({
            "selection_rank": rank,
            "case_id": case.get("case_id"),
            "user_id": case.get("user_id"),
            "conversation_id": case.get("conversation_id"),
            "turn_id": case.get("turn_id"),
            "query": case.get("query"),
            "conversation_history": case.get("conversation_history") or [],
            "conversation_state_before": case.get("conversation_state_before") or {},
            "user_profile": case.get("user_profile") or {},
            "user_memories": case.get("user_memories") or [],
            "reference": case.get("reference") or {},
            "coverage_before_recovery": (
                (case.get("retrieval") or {}).get("coverage_before_recovery") or {}
            ),
            "coverage_after_recovery": coverage,
            "answer_readiness": (
                (case.get("retrieval") or {}).get("answer_readiness") or {}
            ),
            "baseline_final_answer": case.get("final_answer"),
            "baseline_final_answer_scores": case.get("final_answer_scores") or {},
        })

    return {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": source.get("run_id"),
        "source_pipeline_version": source.get("pipeline_version"),
        "selection_strategy": (
            "Lowest coverage_after_recovery; ties use more missing requirements, "
            "then case_id. This is a diagnostic stress subset, not a representative sample."
        ),
        "case_count": len(compact_cases),
        "aggregate_comparison": {
            "selected_low_coverage_cases": _metric_summary(selected),
            "remaining_cases": _metric_summary(remaining),
            "full_run_pearson_correlation_with_coverage": {
                metric: (
                    round(value, 4)
                    if (value := _pearson(cases, metric)) is not None
                    else None
                )
                for metric in FINAL_METRICS
            },
        },
        "cases": compact_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export the lowest-coverage cases as a contextual stress subset."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))
    output = select_cases(source, args.count)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "low_coverage_cases.json"
    ids_path = args.output_dir / "case_ids.txt"
    manifest_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ids_path.write_text(
        "\n".join(case["case_id"] for case in output["cases"]) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "manifest": str(manifest_path),
        "case_ids": str(ids_path),
        "case_count": output["case_count"],
        "aggregate_comparison": output["aggregate_comparison"],
    }, indent=2))


if __name__ == "__main__":
    main()
