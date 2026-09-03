from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from services.external_web_fallback import (
    _empty_answer_status,
    _response_output_text,
    build_external_clarification,
    classify_external_requirements,
    extract_web_sources,
    generate_external_web_answer,
)


class FakeResponse:
    def model_dump(self):
        return {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "type": "search",
                        "sources": [
                            {"url": "https://example.com/consulted", "title": "Consulted"},
                            {
                                "url": "https://tourism.gov.vn/guide",
                                "title": "Official guide",
                                "updated_at": "2026-08-01",
                            },
                            {"url": "javascript:alert(1)", "title": "Unsafe"},
                        ],
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "A cited answer.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://tourism.gov.vn/guide",
                                    "title": "Official guide",
                                    "start_index": 2,
                                    "end_index": 7,
                                }
                            ],
                        }
                    ],
                },
            ]
        }


class FakeRealtimeResponse:
    def __init__(self):
        self.serialization_warnings = None

    def to_dict(self, *, warnings=True):
        self.serialization_warnings = warnings
        return {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "type": "search",
                        "sources": [
                            {"type": "api", "name": "oai-weather"},
                            {"type": "api", "name": "untrusted-feed"},
                        ],
                    },
                }
            ]
        }


class ExternalWebFallbackTests(unittest.TestCase):
    def test_extracts_cited_and_consulted_urls_without_unsafe_schemes(self):
        sources = extract_web_sources(FakeResponse())

        self.assertEqual(
            [source.url for source in sources],
            [
                "https://tourism.gov.vn/guide",
                "https://example.com/consulted",
            ],
        )
        self.assertTrue(sources[0].cited_in_answer)
        self.assertEqual(sources[0].source_type, "official_government")
        self.assertEqual(sources[0].updated_at, "2026-08-01")
        self.assertEqual(sources[0].freshness_metadata_status, "available")
        self.assertFalse(sources[1].cited_in_answer)

    def test_preserves_approved_realtime_weather_feed_without_url(self):
        response = FakeRealtimeResponse()
        sources = extract_web_sources(response)

        self.assertFalse(response.serialization_warnings)
        self.assertEqual(len(sources), 1)
        self.assertIsNone(sources[0].url)
        self.assertEqual(sources[0].domain, "oai-weather")
        self.assertEqual(sources[0].source_type, "real_time_feed")
        self.assertEqual(sources[0].verification_status, "live_provider_feed")
        self.assertEqual(sources[0].freshness_metadata_status, "live_feed")

    def test_recovers_output_text_from_serialized_message(self):
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Recovered answer"}
                    ],
                }
            ]
        }

        self.assertEqual(
            _response_output_text(object(), payload),
            "Recovered answer",
        )

    def test_reports_output_token_exhaustion_precisely(self):
        self.assertEqual(
            _empty_answer_status({
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
            }),
            "incomplete_max_output_tokens",
        )

    @patch.dict(
        "os.environ",
        {
            "EXTERNAL_WEB_FALLBACK_ENABLED": "true",
            "EXTERNAL_WEB_MAX_REQUIREMENTS_PER_CALL": "3",
            "OPENAI_API_KEY": "must-not-be-used",
        },
    )
    def test_complex_request_returns_clarification_without_api_call(self):
        requirements = classify_external_requirements([
            "Current Da Nang weather forecast",
            "Marble Mountains opening hours",
            "Ba Na Hills ticket price",
            "Da Nang to Hoi An shuttle departure schedule",
            "Events in Da Nang this weekend",
        ])

        question, options = build_external_clarification(requirements)
        result = generate_external_web_answer(
            query="Plan my current Da Nang trip",
            rewritten_query="current Da Nang trip",
            missing_requirements=[item.requirement for item in requirements],
            evidence=[],
            parsed=None,
            memory=None,
            requirements=requirements,
        )

        self.assertIn("which group should I check first", question)
        self.assertTrue(all(len(item["requirements"]) <= 3 for item in options))
        self.assertEqual(result.status, "clarification_required")
        self.assertEqual(result.clarification_question, question)
        self.assertGreaterEqual(len(result.clarification_options), 3)

    @patch.dict(
        "os.environ",
        {
            "EXTERNAL_WEB_SEARCH_ONLY_TIME_SENSITIVE": "true",
            "EXTERNAL_WEB_RECENT_MAX_AGE_DAYS": "90",
            "EXTERNAL_WEB_LIVE_MAX_AGE_HOURS": "24",
            "EXTERNAL_WEB_LIVE_CACHE_HOURS": "6",
        },
    )
    def test_classifies_live_recent_and_stable_requirements(self):
        now = datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc)
        requirements = classify_external_requirements(
            [
                "Current Da Nang weather forecast for next week",
                "Ba Na Hills ticket price and opening hours",
                "Typical monthly rainfall and climate",
                "History of the Marble Mountains",
            ],
            now=now,
        )

        self.assertEqual(
            [item.freshness_class for item in requirements],
            ["live", "recent", "stable", "stable"],
        )
        self.assertEqual(
            [item.search_eligible for item in requirements],
            [True, True, False, False],
        )
        self.assertEqual(requirements[0].max_age_hours, 24)
        self.assertEqual(requirements[0].expires_at, "2026-08-12T09:00:00+00:00")
        self.assertEqual(requirements[1].cutoff_date, "2026-05-14")

    @patch.dict(
        "os.environ",
        {"EXTERNAL_WEB_SEARCH_ONLY_TIME_SENSITIVE": "false"},
    )
    def test_can_enable_search_for_stable_requirements(self):
        requirement = classify_external_requirements(
            ["History of Hue"],
            now=datetime(2026, 8, 12, tzinfo=timezone.utc),
        )[0]

        self.assertEqual(requirement.freshness_class, "stable")
        self.assertTrue(requirement.search_eligible)

    @patch.dict(
        "os.environ",
        {
            "EXTERNAL_WEB_FALLBACK_ENABLED": "true",
            "EXTERNAL_WEB_SEARCH_ONLY_TIME_SENSITIVE": "true",
            "OPENAI_API_KEY": "must-not-be-used",
        },
    )
    def test_stable_only_gap_skips_external_api(self):
        result = generate_external_web_answer(
            query="Tell me the history of Hue",
            rewritten_query="Hue history",
            missing_requirements=["History of Hue"],
            evidence=[],
            parsed=None,
            memory=None,
        )

        self.assertEqual(
            result.status,
            "skipped_no_time_sensitive_requirements",
        )
        self.assertFalse(result.succeeded)


if __name__ == "__main__":
    unittest.main()
    build_external_clarification,
