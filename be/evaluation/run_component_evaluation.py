from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from time import perf_counter

import pandas as pd


BE_ROOT = Path(__file__).resolve().parents[1]
if str(BE_ROOT) not in sys.path:
    sys.path.insert(0, str(BE_ROOT))

from services.conversation_memory import (  # noqa: E402
    ConversationState,
    derive_conversation_state,
)
from services.memory import extract_memories  # noqa: E402
from services.query_processing import parse_query, rewrite_query  # noqa: E402


COMPONENTS = {
    "query_rewrite",
    "query_parser",
    "user_memory_extraction",
    "conversation_memory_extraction",
}


def normalize(value: object) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def harmonic_mean(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def concepts_score(text: str, expected: dict) -> dict:
    normalized = normalize(text)
    required = [normalize(item) for item in expected.get("required_concepts") or []]
    forbidden = [normalize(item) for item in expected.get("forbidden_concepts") or []]
    required_hits = sum(item in normalized for item in required)
    forbidden_hits = sum(item in normalized for item in forbidden)
    return {
        "rewrite_concept_recall": required_hits / len(required) if required else 1.0,
        "rewrite_forbidden_rate": forbidden_hits / len(forbidden) if forbidden else 0.0,
        "rewrite_pass": float(required_hits == len(required) and forbidden_hits == 0),
    }


def parser_score(parsed: dict, expected: dict) -> dict:
    expected_location = expected.get("location") or {}
    expected_constraints = expected.get("constraints") or {}
    actual_location = parsed.get("location") or {}
    actual_constraints = parsed.get("constraints") or {}
    checks = {
        "parser_intent_accuracy": normalize(parsed.get("intent")) == normalize(expected.get("intent")),
        "parser_city_accuracy": normalize(actual_location.get("city")) == normalize(expected_location.get("city")),
        "parser_duration_accuracy": actual_constraints.get("duration_days") == expected_constraints.get("duration_days"),
    }
    if "operation" in expected:
        checks["parser_operation_accuracy"] = (
            normalize(parsed.get("operation")) == normalize(expected.get("operation"))
        )
    checks["parser_exact_match"] = all(checks.values())
    return {key: float(value) for key, value in checks.items()}


def memory_items_match(actual: dict, expected: dict) -> bool:
    if actual["memory_type"] != expected["memory_type"]:
        return False
    left = normalize(actual["content"])
    right = normalize(expected["content"])
    return left == right or left in right or right in left


def memory_score(actual: list[dict], expected_case: dict) -> dict:
    expected = expected_case.get("expected_memories") or []
    matched_actual: set[int] = set()
    matched_expected = 0
    for target in expected:
        match = next(
            (
                index
                for index, item in enumerate(actual)
                if index not in matched_actual and memory_items_match(item, target)
            ),
            None,
        )
        if match is not None:
            matched_actual.add(match)
            matched_expected += 1
    precision = len(matched_actual) / len(actual) if actual else float(not expected)
    recall = matched_expected / len(expected) if expected else 1.0
    forbidden_types = set(expected_case.get("forbidden_types") or [])
    forbidden_count = sum(item["memory_type"] in forbidden_types for item in actual)
    return {
        "memory_precision": precision,
        "memory_recall": recall,
        "memory_f1": harmonic_mean(precision, recall),
        "memory_unexpected_count": len(actual) - len(matched_actual),
        "memory_forbidden_count": forbidden_count,
        "memory_exact_match": float(precision == 1 and recall == 1 and forbidden_count == 0),
    }


def list_score(actual: list, expected: list) -> tuple[float, float, float]:
    actual_set = {normalize(item) for item in actual}
    expected_set = {normalize(item) for item in expected}
    overlap = len(actual_set & expected_set)
    precision = overlap / len(actual_set) if actual_set else float(not expected_set)
    recall = overlap / len(expected_set) if expected_set else 1.0
    return precision, recall, harmonic_mean(precision, recall)


def conversation_score(actual: dict, expected: dict) -> dict:
    scalar_fields = [
        "destination",
        "date_from",
        "date_to",
        "duration_days",
        "temporary_budget",
    ]
    applicable = [field for field in scalar_fields if field in expected]
    scalar_results = {
        f"conversation_{field}_accuracy": float(normalize(actual.get(field)) == normalize(expected.get(field)))
        for field in applicable
    }
    for field in ["selected_places", "trip_constraints"]:
        if field in expected:
            precision, recall, f1 = list_score(actual.get(field) or [], expected.get(field) or [])
            scalar_results[f"conversation_{field}_precision"] = precision
            scalar_results[f"conversation_{field}_recall"] = recall
            scalar_results[f"conversation_{field}_f1"] = f1
    scored_values = list(scalar_results.values())
    scalar_results["conversation_field_accuracy"] = sum(scored_values) / len(scored_values) if scored_values else 1.0
    scalar_results["conversation_exact_match"] = float(all(value == 1 for value in scored_values))
    return scalar_results


def evaluate_case(case: dict, components: set[str]) -> list[dict]:
    rows: list[dict] = []
    applicable = set(case.get("applicable_metrics") or []) & components
    rewritten = case["query"]

    if "query_rewrite" in applicable:
        started = perf_counter()
        rewritten = rewrite_query(case["query"], case.get("conversation_history") or [])
        rows.append(
            {
                "case_id": case["case_id"],
                "scenario_type": case["scenario_type"],
                "component": "query_rewrite",
                "input": case["query"],
                "output": rewritten,
                "latency_ms": round((perf_counter() - started) * 1000, 3),
                **concepts_score(rewritten, case["expected_rewrite"]),
            }
        )

    if "query_parser" in applicable:
        started = perf_counter()
        parsed = parse_query(rewritten).model_dump()
        rows.append(
            {
                "case_id": case["case_id"],
                "scenario_type": case["scenario_type"],
                "component": "query_parser",
                "input": rewritten,
                "output": json.dumps(parsed, ensure_ascii=False),
                "latency_ms": round((perf_counter() - started) * 1000, 3),
                **parser_score(parsed, case["expected_parser"]),
            }
        )

    if "user_memory_extraction" in applicable:
        memory_case = case["user_memory_case"]
        started = perf_counter()
        extracted = [item.model_dump() for item in extract_memories(memory_case["message"])]
        rows.append(
            {
                "case_id": case["case_id"],
                "scenario_type": case["scenario_type"],
                "component": "user_memory_extraction",
                "input": memory_case["message"],
                "output": json.dumps(extracted, ensure_ascii=False),
                "latency_ms": round((perf_counter() - started) * 1000, 3),
                **memory_score(extracted, memory_case),
            }
        )

    if "conversation_memory_extraction" in applicable:
        memory_case = case["conversation_memory_case"]
        started = perf_counter()
        state = derive_conversation_state(
            previous=ConversationState.model_validate(memory_case["previous_state"]),
            user_message=memory_case["user_message"],
            assistant_message=memory_case["assistant_message"],
            current_date=date.fromisoformat(memory_case["current_date"]),
            timezone_name=memory_case["timezone"],
        ).model_dump()
        rows.append(
            {
                "case_id": case["case_id"],
                "scenario_type": case["scenario_type"],
                "component": "conversation_memory_extraction",
                "input": json.dumps(memory_case, ensure_ascii=False),
                "output": json.dumps(state, ensure_ascii=False),
                "latency_ms": round((perf_counter() - started) * 1000, 3),
                **conversation_score(state, memory_case["expected_state"]),
            }
        )

    return rows


def visualize(frame: pd.DataFrame, output_dir: Path) -> None:
    import matplotlib.pyplot as plt

    score_columns = [
        "rewrite_pass",
        "parser_exact_match",
        "memory_f1",
        "conversation_field_accuracy",
    ]
    available = [column for column in score_columns if column in frame]
    means = frame[available].mean().dropna()
    figure, axis = plt.subplots(figsize=(9, 5))
    means.plot(kind="bar", ax=axis, color="#10b981")
    axis.set_ylim(0, 1)
    axis.set_title("Component evaluation scores")
    axis.set_ylabel("Score")
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_dir / "component_scores.png", dpi=180)
    plt.close(figure)

    latency = frame.groupby("component")["latency_ms"].mean().sort_values()
    figure, axis = plt.subplots(figsize=(9, 5))
    latency.plot(kind="barh", ax=axis, color="#38bdf8")
    axis.set_title("Mean component latency")
    axis.set_xlabel("Milliseconds")
    axis.grid(axis="x", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_dir / "component_latency.png", dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate rewrite, parser, and memory components")
    parser.add_argument("--dataset", type=Path, default=Path(__file__).parent / "data" / "travel_rag_component_benchmark_v2_100.json")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "runs" / "components")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--components", nargs="*", choices=sorted(COMPONENTS))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    selected = set(args.components or COMPONENTS)
    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    cases = payload["cases"][: args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    failures: list[dict] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['case_id']} ({case['scenario_type']})", flush=True)
        try:
            rows.extend(evaluate_case(case, selected))
        except Exception as exc:
            failures.append(
                {
                    "case_id": case["case_id"],
                    "scenario_type": case["scenario_type"],
                    "error": str(exc),
                }
            )

    frame = pd.DataFrame(rows)
    frame.to_csv(args.output_dir / "component_case_results.csv", index=False, encoding="utf-8-sig")
    (args.output_dir / "component_case_results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = frame.groupby("component").mean(numeric_only=True).reset_index()
    summary.to_csv(args.output_dir / "component_summary.csv", index=False, encoding="utf-8-sig")
    report = [
        "# Component Evaluation Report",
        "",
        f"- Dataset: `{args.dataset}`",
        f"- Cases loaded: {len(cases)}",
        f"- Successful component evaluations: {len(frame)}",
        f"- Failed cases: {len(failures)}",
        "",
        "## Mean scores",
        "",
        summary.to_markdown(index=False),
    ]
    (args.output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if not args.no_plots and not frame.empty:
        visualize(frame, args.output_dir)
    print(summary.to_string(index=False))
    if failures:
        print(f"Failures: {len(failures)} (see failures.json)")


if __name__ == "__main__":
    main()
