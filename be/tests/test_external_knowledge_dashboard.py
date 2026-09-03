from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace

from services.knowledge_gaps import build_external_knowledge_dashboard


class ExternalKnowledgeDashboardTests(unittest.TestCase):
    def test_aggregates_recovery_and_source_statistics(self):
        now = datetime(2026, 8, 12, 12, 0, 0)
        gaps = [
            SimpleNamespace(
                id=1,
                query="What is the current weather?",
                rewritten_query="Current weather in Da Nang",
                missing_requirements=["Current weather", "Rainfall"],
                recovery_queries=["Da Nang current weather"],
                external_sources=[
                    {
                        "id": "W1",
                        "title": "Weather feed",
                        "url": "https://example.com/weather",
                        "domain": "example.com",
                        "source_type": "open_web",
                        "cited_in_answer": True,
                    }
                ],
                external_recovery={
                    "status": "completed",
                    "model": "test-model",
                    "answer_generated": True,
                    "requirements": [
                        {
                            "requirement": "Current weather",
                            "freshness_class": "live",
                            "search_eligible": True,
                            "external_search_status": "completed",
                        }
                    ],
                },
                ingestion_status="pending_review",
                status="open",
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=2,
                query="Tell me the local history",
                rewritten_query=None,
                missing_requirements=["Local history"],
                recovery_queries=[],
                external_sources=[],
                external_recovery={
                    "status": "skipped_no_time_sensitive_requirements",
                    "answer_generated": False,
                },
                ingestion_status="pending_review",
                status="open",
                created_at=now,
                updated_at=now,
            ),
        ]

        dashboard = build_external_knowledge_dashboard(gaps)

        self.assertEqual(dashboard.summary.total_records, 2)
        self.assertEqual(dashboard.summary.pending_review, 2)
        self.assertEqual(dashboard.summary.successful_recoveries, 1)
        self.assertEqual(dashboard.summary.unique_sources, 1)
        self.assertEqual(dashboard.summary.uncovered_requirements, 3)
        self.assertEqual(dashboard.status_counts["completed"], 1)
        self.assertEqual(dashboard.records[0].cited_source_count, 1)
        self.assertEqual(dashboard.records[0].requirements[0].freshness_class, "live")


if __name__ == "__main__":
    unittest.main()
