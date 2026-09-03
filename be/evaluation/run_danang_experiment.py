"""Run a separate 20-query evaluation focused on Da Nang.

This variant keeps the general OpenAI experiment runner unchanged. It creates
one synthetic user with two 10-turn conversations, then reuses the standard
pipeline, judge, and export stages so both experiment versions remain
comparable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import run_openai_experiment as base


CONVERSATIONS = 2
TURNS_PER_CONVERSATION = 10
TOTAL_QUERIES = CONVERSATIONS * TURNS_PER_CONVERSATION
DEFAULT_WORK_DIR = Path(__file__).parent / "runs" / "danang_20"

DANANG_GENERATOR_SYSTEM = base.GENERATOR_SYSTEM + """

Focused benchmark requirements:
- The primary destination is the supplied focus_destination, Da Nang.
- Generate exactly one user and all 20 turns around travel in Da Nang.
- The first turn of each conversation must explicitly name Da Nang.
- Later turns may use natural follow-up wording, but must remain connected to
  the Da Nang trip. Nearby day trips or transport links are allowed only when
  Da Nang remains the starting point or primary destination.
- Cover at least six distinct allowed intents and four distinct allowed
  operations across the 20 turns.
- Include varied questions about attractions, food, accommodation, transport,
  itineraries, activities, culture, practical information, comparisons, and
  personalized constraints where supported by the allowed vocabulary.
- Avoid duplicate or lightly paraphrased queries.
""".strip()


def location_key(value: str) -> str:
    value = value.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(character for character in decomposed if character.isalnum())


def resolve_danang(known_cities: list[str]) -> str:
    matches = [city for city in known_cities if location_key(city) == "danang"]
    if not matches:
        raise RuntimeError(
            "Da Nang is not present in the indexed corpus city list; ingest its data first"
        )
    return matches[0]


def validate_danang_focus(user: dict, destination: str) -> None:
    errors: list[str] = []
    conversations = user.get("conversations", [])
    intents: set[str] = set()
    operations: set[str] = set()

    for conversation in conversations:
        turns = conversation.get("turns", [])
        if not turns:
            continue
        first_turn = turns[0]
        mentions_destination = (
            location_key(destination)
            in location_key(str(first_turn.get("query") or ""))
        )
        has_destination_constraint = any(
            item.get("key") == "city"
            and location_key(str(item.get("value") or ""))
            == location_key(destination)
            for item in first_turn.get("query_constraints", [])
        )
        if not (mentions_destination or has_destination_constraint):
            errors.append(
                f"{conversation.get('conversation_id')}: first turn does not anchor Da Nang"
            )

        for turn in turns:
            intents.add(str(turn.get("intent") or ""))
            operations.add(str(turn.get("operation") or ""))

    if len(intents) < 6:
        errors.append(f"expected at least 6 distinct intents, got {sorted(intents)}")
    if len(operations) < 4:
        errors.append(f"expected at least 4 distinct operations, got {sorted(operations)}")
    if errors:
        raise ValueError("Da Nang focus validation failed: " + "; ".join(errors))


def generate_danang_dataset(output: Path) -> dict:
    client = base.openai_client()
    model = os.environ.get("DATASET_GENERATOR_MODEL", "gpt-5.6-luna")
    known_cities = base.get_known_cities()
    if not known_cities:
        raise RuntimeError("The corpus contains no known cities; ingest data before generation")
    destination = resolve_danang(known_cities)
    api_calls: list[dict] = []
    payload = {
        "user_number": 1,
        "required_user_id": "USER-01",
        "conversation_count": CONVERSATIONS,
        "turns_per_conversation": TURNS_PER_CONVERSATION,
        "total_queries": TOTAL_QUERIES,
        "focus_destination": destination,
        "allowed_intents": base.ALLOWED_QUERY_INTENTS,
        "allowed_operations": base.ALLOWED_QUERY_OPERATIONS,
        "allowed_travel_styles": base.ALLOWED_TRAVEL_STYLES,
        "allowed_activities": base.ALLOWED_ACTIVITIES,
        "allowed_budget_levels": base.ALLOWED_BUDGET_LEVELS,
        "allowed_regions": base.ALLOWED_REGIONS,
        "allowed_place_types": base.ALLOWED_PLACE_TYPES,
        "allowed_suitable_for": base.ALLOWED_SUITABLE_FOR,
        "known_corpus_cities": known_cities,
        "diversity_instruction": (
            "Create broad intent and operation coverage without changing the primary "
            "destination from Da Nang."
        ),
    }

    last_error: Exception | None = None
    print("[generate 1/1] Da Nang-focused user", flush=True)
    for semantic_attempt in range(1, 4):
        result, call_metadata = base.json_completion(
            client,
            model,
            DANANG_GENERATOR_SYSTEM,
            payload,
            base.GeneratedEnvelope,
        )
        user = result.user.model_dump()
        try:
            base.validate_generated_user(
                user,
                expected_user_id="USER-01",
                expected_conversations=CONVERSATIONS,
                expected_turns=TURNS_PER_CONVERSATION,
                known_cities=set(known_cities),
            )
            validate_danang_focus(user, destination)
            api_calls.append({"user_id": "USER-01", **call_metadata})
            break
        except ValueError as exc:
            last_error = exc
            api_calls.append(
                {
                    "user_id": "USER-01",
                    "semantic_attempt": semantic_attempt,
                    "status": "rejected",
                    "reason": str(exc),
                    **call_metadata,
                }
            )
    else:
        raise RuntimeError(
            f"Da Nang generator failed semantic validation after 3 attempts: {last_error}"
        ) from last_error

    dataset = {
        "version": "1.4-danang-focus",
        "generator_model": model,
        "annotation_status": "llm_annotated",
        "experiment_variant": "danang_20",
        "focus_destination": destination,
        "api_calls": api_calls,
        "users": [user],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return dataset


def run_standard_stage(stage: str, work_dir: Path, limit: int | None) -> None:
    command = [
        sys.executable,
        str(Path(base.__file__).resolve()),
        "--stage",
        stage,
        "--work-dir",
        str(work_dir),
    ]
    if limit is not None:
        command.extend(["--limit", str(limit)])
    subprocess.run(command, cwd=base.BE_ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Separate one-user, 20-query Da Nang evaluation"
    )
    parser.add_argument(
        "--stage",
        choices=["generate", "pipeline", "judge", "export", "all"],
        default="all",
    )
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)

    if args.stage in {"generate", "all"}:
        generate_danang_dataset(args.work_dir / "01_generated_dataset.json")
    if args.stage == "all":
        for stage in ("pipeline", "judge", "export"):
            run_standard_stage(stage, args.work_dir, args.limit)
    elif args.stage != "generate":
        run_standard_stage(args.stage, args.work_dir, args.limit)


if __name__ == "__main__":
    main()
