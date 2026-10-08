from contextlib import ExitStack
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from schemas.chat import ChatRequest, ChatResponse
from schemas.pipeline import AnswerReadiness, EvidenceCoverage, ParsedQuery, UserTravelMemory
from services.answer_pipeline import run_chat_pipeline
from services.external_web_fallback import ExternalWebFallbackResult, ExternalWebSource


class ChatWebSearchToggleTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch(
            "services.answer_pipeline.classify_request",
            return_value=SimpleNamespace(category="travel", confidence=1, reason="travel"),
        ))
        stack.enter_context(patch(
            "services.answer_pipeline.get_conversation_memory",
            return_value=SimpleNamespace(summary=""),
        ))
        self.artifacts = SimpleNamespace(
            rewritten_query="Current Da Nang weather",
            reranked_docs=[], recovery_queries=[],
            parsed=ParsedQuery(), memory=UserTravelMemory(),
            coverage=EvidenceCoverage(
                sufficient=False, missing_requirements=["Current Da Nang weather"],
            ),
            answer_readiness=AnswerReadiness(
                mode="insufficient", coverage_ratio=0,
                distinct_supported_place_count=0, minimum_required_place_count=1,
                reason="Missing weather evidence",
            ),
        )
        stack.enter_context(patch(
            "services.answer_pipeline.run_retrieval_pipeline", return_value=self.artifacts,
        ))
        self.external = stack.enter_context(patch(
            "services.answer_pipeline.generate_external_web_answer",
            return_value=ExternalWebFallbackResult(
                status="completed", model="test", answer="Cited web answer",
                sources=[ExternalWebSource(
                    id="W1", url="https://example.com/weather", title="Weather",
                    domain="example.com", source_type="web", cited_in_answer=True,
                )],
            ),
        ))
        self.answer = stack.enter_context(patch(
            "services.answer_pipeline.generate_answer", return_value="Supported database answer",
        ))

    def test_off_blocks_external_call_and_keeps_gap_notice(self):
        events = []
        result = run_chat_pipeline(
            ChatRequest(message="Weather in Da Nang", web_search_enabled=False),
            progress_callback=lambda stage, payload: events.append((stage, payload)),
        )
        self.external.assert_not_called()
        self.answer.assert_not_called()
        self.assertFalse(result.web_search_used)
        self.assertIn("couldn’t find sufficient", result.answer)
        self.assertEqual(result.knowledge_gap["external_recovery"]["status"], "disabled_by_user")
        self.assertTrue(any(payload.get("status") == "disabled_by_user" for _, payload in events))

    def test_off_still_answers_covered_parts(self):
        self.artifacts.coverage.covered_requirements = ["Da Nang attractions"]
        self.artifacts.answer_readiness.mode = "partial"
        result = run_chat_pipeline(ChatRequest(message="Da Nang trip", web_search_enabled=False))
        self.external.assert_not_called()
        self.answer.assert_called_once()
        self.assertEqual(result.answer, "Supported database answer")
        self.assertFalse(result.web_search_used)

    def test_on_uses_cited_web_fallback_for_missing_evidence(self):
        result = run_chat_pipeline(ChatRequest(message="Weather in Da Nang", web_search_enabled=True))
        self.external.assert_called_once()
        self.assertTrue(result.web_search_used)
        self.assertEqual(result.answer, "Cited web answer")
        self.assertEqual(result.sources[0].id, "W1")

    def test_on_does_not_search_when_database_is_sufficient(self):
        self.artifacts.coverage.sufficient = True
        result = run_chat_pipeline(ChatRequest(message="Da Nang attractions"))
        self.external.assert_not_called()
        self.answer.assert_called_once()
        self.assertFalse(result.web_search_used)

    def test_missing_api_key_is_not_reported_as_web_evidence(self):
        self.external.return_value = ExternalWebFallbackResult(status="unavailable", model="test")
        result = run_chat_pipeline(ChatRequest(message="Weather in Da Nang"))
        self.assertFalse(result.web_search_used)
        self.assertIn("couldn’t find sufficient", result.answer)

    def test_switching_mode_does_not_change_other_requests(self):
        database_only = run_chat_pipeline(ChatRequest(message="Weather in Da Nang", web_search_enabled=False))
        with_web = run_chat_pipeline(ChatRequest(message="Weather in Da Nang", web_search_enabled=True))
        self.external.assert_called_once()
        self.assertFalse(database_only.web_search_used)
        self.assertTrue(with_web.web_search_used)
        self.assertNotEqual(database_only.answer, with_web.answer)

    def test_stream_preserves_web_evidence_indicator(self):
        from routers.chat import chat_stream

        async def collect(response):
            events = []
            async for line in response.body_iterator:
                events.append(json.loads(line))
            return events

        with patch("routers.chat.require_session_user_id", return_value=None), \
             patch("routers.chat.SessionLocal"), \
             patch("routers.chat.save_pipeline_telemetry"), \
             patch("routers.chat.run_chat_pipeline", return_value=ChatResponse(
                 answer="Cited web answer", web_search_used=True,
             )):
            events = asyncio.run(collect(chat_stream(
                ChatRequest(message="Weather in Da Nang"), http_request=None,
            )))
        self.assertEqual(events[-1]["type"], "complete")
        self.assertTrue(events[-1]["web_search_used"])


if __name__ == "__main__":
    unittest.main()
