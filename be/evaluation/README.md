# Headless RAG Evaluation

This directory contains a 100-case synthetic Vietnam travel benchmark and a headless evaluator for the real backend pipeline.

## Important validity note

The generated cases use weak labels based on expected places, locations, and keywords. They are suitable for pipeline development and preliminary experiments, but they are not human ground truth.

Before reporting Recall@K or nDCG in the thesis, review each case and populate `relevant_chunk_ids` with judged IDs from the actual corpus. Change `annotation_status` to `human_annotated` after review.

## Run retrieval evaluation

From the `be` directory:

```powershell
python evaluation/run_evaluation.py
```

Quick smoke test:

```powershell
python evaluation/run_evaluation.py --limit 5
```

Skip PNG generation when Matplotlib is not installed:

```powershell
python evaluation/run_evaluation.py --limit 5 --no-plots
```

## Run end-to-end answer evaluation

```powershell
python evaluation/run_evaluation.py --generate
```

Add DeepSeek-as-judge scoring:

```powershell
python evaluation/run_evaluation.py --generate --judge
```

Generation and judging make additional paid model calls. For 100 cases, `--generate --judge` makes approximately 200 DeepSeek calls in addition to calls already used by query processing.

## Outputs

Results are written to `evaluation/results/`:

- `case_results.csv`
- `case_results.json`
- `summary.json`
- `retrieval_metrics.png`
- `latency_by_stage.png`
- `recall_by_intent.png`

## Stage and ablation evaluation

Run a quick two-configuration comparison:

```powershell
python evaluation/run_ablation.py --limit 5 --configs full no_reranker
```

Run every configured ablation with pooled LLM chunk judgments:

```powershell
python evaluation/run_ablation.py --judge-retrieval
```

Run retrieval, final generation, and answer judging:

```powershell
python evaluation/run_ablation.py --judge-retrieval --generate --judge-answers
```

Retrieval judgments are cached per case under the run's `judgments/` directory and reused on later runs. The runner exports complete stage traces, pooled judgments, per-case metrics, stage summaries, ablation summaries, and comparison charts.

Because the CLI loads its own embedding and reranker models, stop the FastAPI development server before a large ablation run on memory-constrained machines. Running the API and evaluator together can load multiple model copies and exhaust RAM.

Additional ablation outputs include:

- `report.md`
- `component_contributions.csv`
- `retrieval_by_stage.png`
- `ablation_retrieval.png`
- `ablation_answer_quality.png`
- `ablation_latency.png`

## Component benchmark v2

The original retrieval benchmark is preserved. A separate 100-case dataset evaluates query rewriting, parsing, user-memory extraction, and conversation-state extraction:

```text
evaluation/data/travel_rag_component_benchmark_v2_100.json
```

Run all applicable component metrics:

```powershell
python evaluation/run_component_evaluation.py
```

Run only a subset:

```powershell
python evaluation/run_component_evaluation.py --components query_rewrite query_parser
```

Quick smoke test:

```powershell
python evaluation/run_component_evaluation.py --limit 3 --no-plots
```

Outputs include per-case JSON/CSV traces, failures, component summaries, a Markdown report, score charts, and latency charts.

## Environment requirements

The evaluator requires the same database, model, and API-key environment variables as the backend. It imports backend services directly and does not require Angular, Google login, or HTTP cookies.

## Nine-metric thesis evaluation

`run_thesis_evaluation.py` implements the agreed primary metrics:

- Understanding: Intent Accuracy, Operation Accuracy, and Query Constraint F1
- Retrieval: graded chunk relevance (0–3), nDCG@5, and Precision@5 using relevance ≥ 2
- Final answer: Correctness, Faithfulness, Personalization Adherence, Completeness

Copy `evaluation/data/thesis_evaluation_template.json` and replace its reference labels and
pipeline predictions. Reference labels should be reviewed by a human before final reporting.

Run deterministic metrics and export judge packets without an API key:

```powershell
python evaluation/run_thesis_evaluation.py --dataset evaluation/data/thesis_evaluation_template.json
```

This writes `case_metrics.csv`, `case_metrics.json`, `judge_packets.json`,
`human_review_template.csv`, and `summary.json`.
The four final-answer metrics remain null until scores are supplied or an LLM judge is enabled.

Later, configure `OPENAI_API_KEY` in `.env` (or the shell environment). The default judge is
OpenAI `gpt-5.6-terra`; change `JUDGE_MODEL` if that model is unavailable to your API project.
Run the OpenAI judge with:

```powershell
python evaluation/run_thesis_evaluation.py --dataset evaluation/data/your_dataset.json --judge
```

For another OpenAI-compatible endpoint, set `JUDGE_BASE_URL`, `JUDGE_API_KEY`, and
`JUDGE_MODEL`, then run:

```powershell
python evaluation/run_thesis_evaluation.py --dataset evaluation/data/your_dataset.json --judge --judge-provider openai-compatible
```

The exact model ID, judge prompt, provider, dataset version, and run date should be recorded for
reproducibility. Human reviewers should score a stratified 20–30% sample independently before
seeing the LLM scores.

## Full OpenAI experiment workflow

`run_openai_experiment.py` connects the complete experiment:

1. OpenAI generates five controlled users and their multi-turn queries.
2. The existing application pipeline performs understanding, planning, retrieval, checking,
   recovery, and final-answer generation. Complete stage traces are saved.
3. A separate OpenAI judge grades pooled retrieval candidates and final answers.
4. The run is exported into the validated nine-metric thesis schema.

Configure these values in `be/.env`:

```dotenv
OPENAI_API_KEY=replace-with-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
DATASET_GENERATOR_MODEL=gpt-5.6-luna
JUDGE_MODEL=gpt-5.6-terra
```

The application pipeline still needs its normal database and answer-model environment variables.
Run each stage separately so the generated dataset can be reviewed and frozen before answers are
produced:

```powershell
python evaluation/run_openai_experiment.py --stage generate
python evaluation/run_openai_experiment.py --stage pipeline
python evaluation/run_openai_experiment.py --stage judge
python evaluation/run_openai_experiment.py --stage export
```

The defaults generate 5 users × 2 conversations × 10 turns = 100 queries. For a one-case smoke
test:

```powershell
python evaluation/run_openai_experiment.py --stage generate --users 1 --conversations 1 --turns 1
python evaluation/run_openai_experiment.py --stage pipeline --limit 1
python evaluation/run_openai_experiment.py --stage judge --limit 1
python evaluation/run_openai_experiment.py --stage export
```

Artifacts are written under `evaluation/runs/openai_experiment/` as
`01_generated_dataset.json`, `02_pipeline_traces.json`, `03_judged_traces.json`, and
`04_thesis_dataset.json`. The nine aggregate metrics are saved in `05_metric_summary.json`.

Generated and LLM-judged annotations remain marked `llm_annotated`. Change the status to
`human_annotated` only after independent human review.
