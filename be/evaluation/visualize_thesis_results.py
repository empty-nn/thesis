from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from .run_thesis_evaluation import deterministic_metrics
    from .thesis_evaluation_schema import ThesisDataset
except ImportError:  # Direct script execution from the evaluation directory.
    from run_thesis_evaluation import deterministic_metrics
    from thesis_evaluation_schema import ThesisDataset


UNDERSTANDING_METRICS = [
    "intent_accuracy",
    "operation_accuracy",
    "query_constraint_f1",
    "retrieval_facet_f1",
]
RETRIEVAL_METRICS = ["ndcg_at_5", "precision_at_5"]
ANSWER_METRICS = [
    "correctness",
    "faithfulness",
    "personalization_adherence",
    "completeness",
]
ALL_METRICS = UNDERSTANDING_METRICS + RETRIEVAL_METRICS + ANSWER_METRICS

DISPLAY_NAMES = {
    "intent_accuracy": "Intent\naccuracy",
    "operation_accuracy": "Operation\naccuracy",
    "query_constraint_f1": "Constraint\nF1",
    "retrieval_facet_f1": "Facet\nF1",
    "ndcg_at_5": "nDCG@5",
    "precision_at_5": "Precision@5",
    "correctness": "Correctness",
    "faithfulness": "Faithfulness",
    "personalization_adherence": "Personalization\nadherence",
    "completeness": "Completeness",
}

COLORS = {
    "understanding": "#2563EB",
    "retrieval": "#059669",
    "answer": "#D97706",
    "accent": "#7C3AED",
}


def configure_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 130,
            "savefig.dpi": 300,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.alpha": 0.22,
            "grid.linestyle": "--",
        }
    )


def load_cases(dataset_path: Path) -> tuple[ThesisDataset, pd.DataFrame]:
    dataset = ThesisDataset.model_validate_json(dataset_path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for case in dataset.cases:
        row = {
            "case_id": case.case_id,
            "user_id": case.user_id,
            "conversation_id": case.conversation_id,
            "turn_id": case.turn_id,
            "intent": case.reference.intent,
            **deterministic_metrics(case),
        }
        scores = case.prediction.final_answer_scores
        if scores is not None:
            row.update(scores.model_dump(exclude={"rationale", "judge_model"}))
        rows.append(row)
    return dataset, pd.DataFrame(rows)


def annotate_bars(axis: plt.Axes, decimals: int = 2) -> None:
    for patch in axis.patches:
        height = patch.get_height()
        if np.isfinite(height):
            axis.annotate(
                f"{height:.{decimals}f}",
                (patch.get_x() + patch.get_width() / 2, height),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
            )


def metric_overview(frame: pd.DataFrame, output_dir: Path) -> None:
    groups = [
        ("Query understanding", UNDERSTANDING_METRICS, COLORS["understanding"], (0, 1)),
        ("Retrieval", RETRIEVAL_METRICS, COLORS["retrieval"], (0, 1)),
        ("Final answer", ANSWER_METRICS, COLORS["answer"], (1, 5)),
    ]
    figure, axes = plt.subplots(1, 3, figsize=(15, 5.2), constrained_layout=True)
    for axis, (title, metrics, color, limits) in zip(axes, groups, strict=True):
        available = [metric for metric in metrics if metric in frame]
        means = frame[available].mean()
        axis.bar(
            [DISPLAY_NAMES[metric] for metric in available],
            means.values,
            color=color,
            width=0.68,
        )
        axis.set_title(title)
        axis.set_ylim(*limits)
        axis.set_ylabel("Mean score")
        axis.tick_params(axis="x", labelrotation=0)
        annotate_bars(axis)
    figure.suptitle(f"Evaluation metric overview (N={len(frame)})", fontsize=15, fontweight="bold")
    figure.savefig(output_dir / "01_metric_overview.png", bbox_inches="tight")
    plt.close(figure)


def answer_distributions(frame: pd.DataFrame, output_dir: Path) -> None:
    available = [metric for metric in ANSWER_METRICS if metric in frame]
    if not available:
        return
    figure, axis = plt.subplots(figsize=(9.5, 5.5), constrained_layout=True)
    values = [frame[metric].dropna().to_numpy() for metric in available]
    boxes = axis.boxplot(
        values,
        tick_labels=[DISPLAY_NAMES[metric] for metric in available],
        patch_artist=True,
        showmeans=True,
        meanprops={"marker": "D", "markerfacecolor": "white", "markeredgecolor": "#111827"},
        medianprops={"color": "#111827", "linewidth": 1.6},
    )
    for box in boxes["boxes"]:
        box.set_facecolor(COLORS["answer"])
        box.set_alpha(0.72)
    axis.set_ylim(0.8, 5.2)
    axis.set_yticks([1, 2, 3, 4, 5])
    axis.set_ylabel("LLM judge score (1–5)")
    axis.set_title(f"Final-answer score distributions (N={len(frame)})", fontweight="bold")
    axis.text(
        0.99,
        0.02,
        "Diamond = mean; line = median",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="#4B5563",
    )
    figure.savefig(output_dir / "02_answer_score_distributions.png", bbox_inches="tight")
    plt.close(figure)


def normalized_metric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for metric in ANSWER_METRICS:
        if metric in normalized:
            normalized[metric] = normalized[metric] / 5.0
    return normalized


def heatmap(
    values: pd.DataFrame,
    title: str,
    output_path: Path,
    y_label: str,
) -> None:
    if values.empty:
        return
    figure_width = max(13, 1.25 * len(values.columns))
    figure_height = max(3.8, 0.62 * len(values.index) + 1.8)
    figure, axis = plt.subplots(figsize=(figure_width, figure_height), constrained_layout=True)
    image = axis.imshow(values.to_numpy(), cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
    axis.set_xticks(range(len(values.columns)))
    axis.set_xticklabels([DISPLAY_NAMES.get(column, column) for column in values.columns])
    axis.tick_params(axis="x", labelsize=9)
    axis.set_yticks(range(len(values.index)))
    axis.set_yticklabels(values.index)
    axis.set_ylabel(y_label)
    axis.set_title(title, fontweight="bold")
    for row in range(len(values.index)):
        for column in range(len(values.columns)):
            value = values.iat[row, column]
            text_color = "white" if value >= 0.62 else "#111827"
            axis.text(column, row, f"{value:.2f}", ha="center", va="center", color=text_color, fontsize=8.5)
    colorbar = figure.colorbar(image, ax=axis, fraction=0.025, pad=0.02)
    colorbar.set_label("Normalized mean score (0–1)")
    figure.savefig(output_path, bbox_inches="tight")
    plt.close(figure)


def group_heatmaps(frame: pd.DataFrame, output_dir: Path) -> None:
    normalized = normalized_metric_frame(frame)
    metrics = [metric for metric in ALL_METRICS if metric in normalized]

    per_user = normalized.groupby("user_id", sort=True)[metrics].mean()
    per_user.to_csv(output_dir / "per_user_metric_means_normalized.csv", encoding="utf-8-sig")
    heatmap(
        per_user,
        "Normalized performance by user profile",
        output_dir / "03_per_user_heatmap.png",
        "User profile",
    )

    per_intent = normalized.groupby("intent", sort=True)[metrics].mean()
    per_intent.to_csv(output_dir / "per_intent_metric_means_normalized.csv", encoding="utf-8-sig")
    heatmap(
        per_intent,
        "Normalized performance by query intent",
        output_dir / "04_per_intent_heatmap.png",
        "Reference intent",
    )


def pearson(x: pd.Series, y: pd.Series) -> float:
    paired = pd.concat([x, y], axis=1).dropna()
    if len(paired) < 2 or paired.iloc[:, 0].nunique() < 2 or paired.iloc[:, 1].nunique() < 2:
        return float("nan")
    return float(paired.iloc[:, 0].corr(paired.iloc[:, 1]))


def retrieval_answer_relationships(frame: pd.DataFrame, output_dir: Path) -> None:
    pairs = [
        ("ndcg_at_5", "correctness"),
        ("precision_at_5", "faithfulness"),
        ("ndcg_at_5", "completeness"),
    ]
    available_pairs = [(x, y) for x, y in pairs if x in frame and y in frame]
    if not available_pairs:
        return
    figure, axes = plt.subplots(1, len(available_pairs), figsize=(5.1 * len(available_pairs), 4.8), constrained_layout=True)
    axes_array = np.atleast_1d(axes)
    correlations: list[dict] = []
    for axis, (x_name, y_name) in zip(axes_array, available_pairs, strict=True):
        paired = frame[[x_name, y_name]].dropna()
        x = paired[x_name].to_numpy(dtype=float)
        y = paired[y_name].to_numpy(dtype=float)
        axis.scatter(x, y, alpha=0.68, s=34, color=COLORS["accent"], edgecolors="white", linewidths=0.45)
        if len(x) >= 2 and np.ptp(x) > 0:
            slope, intercept = np.polyfit(x, y, 1)
            line_x = np.linspace(x.min(), x.max(), 100)
            axis.plot(line_x, slope * line_x + intercept, color="#DC2626", linewidth=1.8)
        correlation = pearson(paired[x_name], paired[y_name])
        correlations.append({"retrieval_metric": x_name, "answer_metric": y_name, "pearson_r": correlation})
        axis.set_xlim(-0.03, 1.03)
        axis.set_ylim(0.8, 5.2)
        axis.set_xlabel(DISPLAY_NAMES[x_name])
        axis.set_ylabel(f"{DISPLAY_NAMES[y_name]} (1–5)")
        axis.set_title(f"Pearson r = {correlation:.2f}" if np.isfinite(correlation) else "Pearson r = N/A")
    figure.suptitle("Relationship between retrieval and final-answer quality", fontsize=14, fontweight="bold")
    figure.savefig(output_dir / "05_retrieval_answer_relationships.png", bbox_inches="tight")
    plt.close(figure)
    pd.DataFrame(correlations).to_csv(output_dir / "retrieval_answer_correlations.csv", index=False, encoding="utf-8-sig")


def telemetry_charts(summary_path: Path | None, output_dir: Path) -> None:
    if summary_path is None or not summary_path.exists():
        return
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    telemetry = summary.get("telemetry_by_stage", {})
    if not telemetry:
        return
    rows = []
    for stage, values in telemetry.items():
        calls = int(values.get("call_count") or 0)
        rows.append(
            {
                "stage": stage.replace("_", " ").title(),
                "mean_latency_ms": (values.get("latency_ms") or 0) / calls if calls else 0,
                "tokens_per_call": (values.get("total_tokens") or 0) / calls if calls else 0,
                "estimated_cost_usd": values.get("estimated_cost_usd") or 0,
            }
        )
    telemetry_frame = pd.DataFrame(rows).sort_values("mean_latency_ms", ascending=True)
    telemetry_frame.to_csv(output_dir / "telemetry_by_stage.csv", index=False, encoding="utf-8-sig")

    figure, axes = plt.subplots(1, 3, figsize=(16, max(5, 0.48 * len(telemetry_frame))), constrained_layout=True)
    configurations = [
        ("mean_latency_ms", "Mean latency per call (ms)", COLORS["understanding"]),
        ("tokens_per_call", "Mean tokens per call", COLORS["retrieval"]),
        ("estimated_cost_usd", "Estimated total cost (USD)", COLORS["answer"]),
    ]
    for axis, (column, title, color) in zip(axes, configurations, strict=True):
        axis.barh(telemetry_frame["stage"], telemetry_frame[column], color=color, alpha=0.82)
        axis.set_title(title)
        axis.set_xlabel(title)
    figure.suptitle("Pipeline efficiency by stage", fontsize=15, fontweight="bold")
    figure.savefig(output_dir / "06_pipeline_efficiency.png", bbox_inches="tight")
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate thesis-ready visualizations from an exported evaluation dataset")
    parser.add_argument("--dataset", type=Path, required=True, help="Path to 04_thesis_dataset.json")
    parser.add_argument(
        "--summary",
        type=Path,
        help="Path to 05_metric_summary.json; defaults to the dataset's sibling file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory; defaults to a visualizations folder beside the dataset",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_path = args.dataset.resolve()
    summary_path = args.summary.resolve() if args.summary else dataset_path.with_name("05_metric_summary.json")
    output_dir = args.output_dir.resolve() if args.output_dir else dataset_path.parent / "visualizations"
    output_dir.mkdir(parents=True, exist_ok=True)

    configure_style()
    _, frame = load_cases(dataset_path)
    if frame.empty:
        raise ValueError(f"Dataset contains no evaluation cases: {dataset_path}")
    frame.to_csv(output_dir / "case_metrics.csv", index=False, encoding="utf-8-sig")

    metric_overview(frame, output_dir)
    answer_distributions(frame, output_dir)
    group_heatmaps(frame, output_dir)
    retrieval_answer_relationships(frame, output_dir)
    telemetry_charts(summary_path, output_dir)

    manifest = {
        "dataset": str(dataset_path),
        "summary": str(summary_path) if summary_path.exists() else None,
        "case_count": len(frame),
        "user_count": int(frame["user_id"].nunique()),
        "intent_count": int(frame["intent"].nunique()),
        "generated_files": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
    }
    (output_dir / "visualization_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
