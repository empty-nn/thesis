from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from data_building.extract_metadata.extractor import (
    DEEPSEEK_FAST_MODEL,
    get_deepseek_client,
)
from services.llm_telemetry import create_chat_completion


class RequestRoute(BaseModel):
    category: Literal["travel", "out_of_scope", "ambiguous"] = "travel"
    confidence: float = 0.5
    reason: str = ""
    clarification_question: str | None = None


def classify_request(
    query: str,
    conversation_history: list[dict],
    model: str = DEEPSEEK_FAST_MODEL,
) -> RequestRoute:
    history_text = "\n".join(
        f"{item.get('role', 'unknown')}: {item.get('content', '')}"
        for item in conversation_history[-4:]
    )
    system_prompt = """
Classify a request for a Vietnam travel assistant.

Categories:
- travel: destinations, itineraries, attractions, food, accommodation,
  transport, events, budgets, dates, or follow-ups to a travel conversation.
- out_of_scope: clearly unrelated requests such as programming, mathematics,
  general writing, or non-travel professional advice.
- ambiguous: too unclear to determine the travel information need.

Use recent history to understand follow-up references. Do not answer the user.
Return JSON only:
{
  "category": "travel|out_of_scope|ambiguous",
  "confidence": 0.0,
  "reason": "short reason",
  "clarification_question": null
}
""".strip()
    try:
        client = get_deepseek_client()
        response = create_chat_completion(
            "request_routing", client,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Recent conversation:\n{history_text or 'None'}\n\n"
                        f"Current request:\n{query}"
                    ),
                },
            ],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("empty routing result")
        return RequestRoute.model_validate(json.loads(content))
    except Exception as exc:
        print(f"[REQUEST ROUTER WARNING] {exc}")
        # Preserve service availability if classification fails. Retrieval and
        # the evidence gate still prevent unsupported factual answers.
        return RequestRoute(
            category="travel",
            confidence=0.0,
            reason="Router unavailable; continued with guarded retrieval.",
        )
