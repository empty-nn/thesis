from __future__ import annotations

import unittest

from services.llm_telemetry import _response_dict


class FakeTypedResponse:
    def __init__(self):
        self.warnings = None

    def to_dict(self, *, warnings=True):
        self.warnings = warnings
        return {"output": [{"type": "web_search_call"}]}


class LLMTelemetryTests(unittest.TestCase):
    def test_response_serialization_disables_sdk_schema_warnings(self):
        response = FakeTypedResponse()

        payload = _response_dict(response)

        self.assertFalse(response.warnings)
        self.assertEqual(payload["output"][0]["type"], "web_search_call")


if __name__ == "__main__":
    unittest.main()
