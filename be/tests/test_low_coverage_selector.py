from __future__ import annotations

import unittest

from evaluation.select_low_coverage_cases import select_cases


def _case(case_id: str, coverage: float, completeness: float) -> dict:
    return {
        "case_id": case_id,
        "user_id": "USER-01",
        "conversation_id": "CONV-01",
        "turn_id": 1,
        "query": case_id,
        "retrieval": {
            "coverage_after_recovery": {
                "coverage_ratio": coverage,
                "missing_count": int(coverage < 1),
            }
        },
        "final_answer_scores": {
            "correctness": 4,
            "faithfulness": 4,
            "personalization_adherence": 4,
            "completeness": completeness,
        },
    }


class LowCoverageSelectorTests(unittest.TestCase):
    def test_selects_lowest_coverage_and_preserves_context_fields(self):
        source = {
            "run_id": "run-test",
            "pipeline_version": "test",
            "cases": [
                _case("high", 1.0, 5),
                _case("lowest", 0.0, 1),
                _case("middle", 0.5, 3),
            ],
        }

        result = select_cases(source, 2)

        self.assertEqual(
            [case["case_id"] for case in result["cases"]],
            ["lowest", "middle"],
        )
        self.assertEqual(result["case_count"], 2)
        self.assertIn("aggregate_comparison", result)


if __name__ == "__main__":
    unittest.main()
