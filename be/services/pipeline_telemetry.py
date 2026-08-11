from __future__ import annotations

from db.full_model import PipelineTelemetryORM
from db.session import SessionLocal


def save_pipeline_telemetry(
    snapshot: dict,
    *,
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        db.add(PipelineTelemetryORM(
            request_id=snapshot["request_id"],
            user_id=user_id,
            conversation_id=conversation_id,
            status=snapshot["status"],
            error_type=snapshot.get("error_type"),
            total_latency_ms=snapshot["total_latency_ms"],
            total_tokens=snapshot["totals"]["total_tokens"],
            estimated_cost_usd=snapshot.get("estimated_cost_usd"),
            stage_records=snapshot["stages"],
            token_totals=snapshot["totals"],
            pricing_snapshot=snapshot["pricing"],
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"[PIPELINE TELEMETRY WARNING] {exc}")
    finally:
        db.close()
