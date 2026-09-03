from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Iterator


def pricing_snapshot() -> dict[str, Any]:
    raw = os.environ.get("LLM_PRICING_USD_PER_1M_JSON", "{}")
    try:
        models = json.loads(raw)
        if not isinstance(models, dict):
            models = {}
    except json.JSONDecodeError:
        models = {}
    return {
        "currency": "USD",
        "unit": "per_1m_tokens",
        "effective_date": os.environ.get("LLM_PRICING_EFFECTIVE_DATE"),
        "source": os.environ.get("LLM_PRICING_SOURCE", "operator_configured"),
        "models": models,
    }


def _usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {
        key: getattr(usage, key)
        for key in dir(usage)
        if not key.startswith("_") and isinstance(getattr(usage, key), (int, float, dict))
    }


def _response_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "to_dict"):
        value = response.to_dict(warnings=False)
        return value if isinstance(value, dict) else {}
    if hasattr(response, "model_dump"):
        try:
            value = response.model_dump(warnings=False)
        except TypeError:
            value = response.model_dump()
        return value if isinstance(value, dict) else {}
    return response if isinstance(response, dict) else {}


def normalize_usage(response: Any) -> dict[str, int]:
    usage = _usage_dict(response)
    input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
    output_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    if hasattr(details, "model_dump"):
        details = details.model_dump()
    cached_tokens = int((details or {}).get("cached_tokens", 0) or 0)
    cached_tokens = min(cached_tokens, input_tokens)
    total_value = usage.get("total_tokens")
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "uncached_input_tokens": input_tokens - cached_tokens,
        "output_tokens": output_tokens,
        "total_tokens": (
            int(total_value)
            if total_value is not None
            else input_tokens + output_tokens
        ),
    }


def estimate_cost_usd(model: str, usage: dict[str, int], pricing: dict) -> float | None:
    rates = pricing.get("models", {}).get(model)
    if not isinstance(rates, dict):
        return None
    input_rate = float(rates.get("input", 0) or 0)
    cached_rate = float(rates.get("cached_input", input_rate) or 0)
    output_rate = float(rates.get("output", 0) or 0)
    return round((
        usage["uncached_input_tokens"] * input_rate
        + usage["cached_input_tokens"] * cached_rate
        + usage["output_tokens"] * output_rate
    ) / 1_000_000, 10)


@dataclass
class LLMTelemetryCollector:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_perf: float = field(default_factory=perf_counter)
    pricing: dict[str, Any] = field(default_factory=pricing_snapshot)
    stages: list[dict[str, Any]] = field(default_factory=list)
    status: str = "complete"
    error_type: str | None = None

    def record(self, stage: str, model: str, response: Any, latency_ms: float) -> None:
        try:
            usage = normalize_usage(response)
            payload = _response_dict(response)
            web_search_call_count = sum(
                isinstance(item, dict) and item.get("type") == "web_search_call"
                for item in (payload.get("output") or [])
            ) if isinstance(payload, dict) else 0
            self.stages.append({
                "stage": stage,
                "model": model,
                "latency_ms": round(latency_ms, 3),
                **usage,
                "web_search_call_count": web_search_call_count,
                "estimated_cost_usd": estimate_cost_usd(model, usage, self.pricing),
            })
        except Exception as exc:
            print(f"[LLM TELEMETRY WARNING] {exc}")

    def mark_failed(self, exc: Exception) -> None:
        self.status = "failed"
        self.error_type = type(exc).__name__

    def snapshot(self) -> dict[str, Any]:
        totals = {
            "input_tokens": sum(item["input_tokens"] for item in self.stages),
            "cached_input_tokens": sum(item["cached_input_tokens"] for item in self.stages),
            "uncached_input_tokens": sum(item["uncached_input_tokens"] for item in self.stages),
            "output_tokens": sum(item["output_tokens"] for item in self.stages),
            "total_tokens": sum(item["total_tokens"] for item in self.stages),
        }
        known_costs = [
            item["estimated_cost_usd"] for item in self.stages
            if item["estimated_cost_usd"] is not None
        ]
        return {
            "request_id": self.request_id,
            "status": self.status,
            "error_type": self.error_type,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_latency_ms": round((perf_counter() - self.started_perf) * 1000, 3),
            "stages": self.stages,
            "totals": totals,
            "estimated_cost_usd": round(sum(known_costs), 10) if known_costs else None,
            "pricing": self.pricing,
        }


_CURRENT: ContextVar[LLMTelemetryCollector | None] = ContextVar(
    "llm_telemetry_collector", default=None
)


@contextmanager
def telemetry_session(request_id: str | None = None) -> Iterator[LLMTelemetryCollector]:
    collector, token = activate_telemetry(request_id)
    try:
        yield collector
    except Exception as exc:
        collector.mark_failed(exc)
        raise
    finally:
        _CURRENT.reset(token)


def activate_telemetry(request_id: str | None = None) -> tuple[LLMTelemetryCollector, Any]:
    collector = LLMTelemetryCollector(request_id=request_id or str(uuid.uuid4()))
    return collector, _CURRENT.set(collector)


def deactivate_telemetry(token: Any) -> None:
    _CURRENT.reset(token)


def record_llm_response(stage: str, model: str, response: Any, started: float) -> None:
    collector = _CURRENT.get()
    if collector is not None:
        collector.record(stage, model, response, (perf_counter() - started) * 1000)


def create_chat_completion(stage: str, client: Any, **kwargs: Any) -> Any:
    model = str(kwargs.get("model") or "unknown")
    if model.startswith("deepseek-v4-"):
        # V4 defaults to thinking mode. Most pipeline calls have bounded JSON
        # outputs; a reasoning trace can consume max_tokens before `content`
        # is emitted. Keep thinking explicit and off unless a caller opts in.
        thinking_enabled = bool(kwargs.pop("deepseek_thinking", False))
        extra_body = dict(kwargs.pop("extra_body", {}) or {})
        extra_body.setdefault(
            "thinking",
            {"type": "enabled" if thinking_enabled else "disabled"},
        )
        kwargs["extra_body"] = extra_body
    started = perf_counter()
    response = client.chat.completions.create(**kwargs)
    record_llm_response(stage, model, response, started)
    return response


def create_response(stage: str, client: Any, **kwargs: Any) -> Any:
    model = str(kwargs.get("model") or "unknown")
    started = perf_counter()
    response = client.responses.create(**kwargs)
    record_llm_response(stage, model, response, started)
    return response
