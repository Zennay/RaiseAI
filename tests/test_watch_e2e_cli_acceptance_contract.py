"""CLI-level regression gates for schema-v2 Watch -> gateway -> provider evidence.

The fixtures are synthetic and do not establish physical Galaxy Watch 7 PASS.
The frozen v1.5.2 APK, gateway and physical acceptance workflow are untouched.
"""

from contextlib import redirect_stdout
from io import StringIO
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "raise_e2e_cli_matrix", ROOT / "tools" / "validate-watch-e2e-evidence.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Watch E2E evidence validator unavailable")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

FROZEN_SHA = "8f719bb273f9b997848864f342598e7df5f090e5"


def successful_evidence(**overrides):
    evidence = {
        "schema_version": 2,
        "recorded_at_utc": "2026-10-03T23:40:00Z",
        "app_version": "1.5.2",
        "source_revision": FROZEN_SHA,
        "outcome": "success",
        "input_length_chars": 24,
        "latency_ms": 740,
        "route": "quick_ai",
        "status": "ok",
        "execution_enabled": False,
        "execution_reason_present": False,
        "answer_present": True,
    }
    evidence.update(overrides)
    return evidence


class WatchE2eCliAcceptanceContract(unittest.TestCase):
    """Exercise the executable CLI, not just the in-process validator."""

    def invoke(self, payload, *flags, raw=None):
        with tempfile.TemporaryDirectory(prefix="raise-e2e-cli-") as tmp:
            path = Path(tmp) / "watch-e2e-evidence.json"
            path.write_text(
                json.dumps(payload) if raw is None else raw,
                encoding="utf-8",
            )
            captured = StringIO()
            with redirect_stdout(captured):
                exit_code = validator.main([str(path), *flags])
        return exit_code, json.loads(captured.getvalue())

    def test_strict_frozen_quick_ai_contract_passes_without_response_text(self):
        code, output = self.invoke(
            successful_evidence(),
            "--expect-route", "quick_ai",
            "--expect-status", "ok",
            "--require-answer",
            "--expect-app-version", "1.5.2",
            "--expect-source-revision", FROZEN_SHA,
            "--max-latency-ms", "750",
        )
        self.assertEqual(code, 0)
        self.assertTrue(output["valid"])
        self.assertEqual(output["source_revision"], FROZEN_SHA)
        self.assertTrue(output["answer_present"])
        self.assertEqual(output["latency_ms"], 740)
        self.assertNotIn("answer_text", output)
        self.assertNotIn("watch_serial", output)

    def test_missing_answer_cannot_pass_strict_cli(self):
        code, output = self.invoke(
            successful_evidence(answer_present=False),
            "--require-answer",
        )
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIn("answer/message", output["reason"])

    def test_failed_request_cannot_masquerade_as_success(self):
        failure = {
            key: value
            for key, value in successful_evidence().items()
            if key in validator.COMMON_KEYS
        }
        failure["outcome"] = "failure"
        failure["error_code"] = "gateway_http_503"
        code, output = self.invoke(failure, "--require-answer")
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIn("Watch E2E request failed", output["reason"])

    def test_wrong_route_is_not_accepted_as_quick_ai(self):
        code, output = self.invoke(
            successful_evidence(route="deep_ai"), "--expect-route", "quick_ai"
        )
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIn("does not match expected", output["reason"])

    def test_wrong_frozen_source_is_rejected(self):
        code, output = self.invoke(
            successful_evidence(source_revision="0" * 40),
            "--expect-source-revision", FROZEN_SHA,
        )
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIn("source_revision", output["reason"])

    def test_private_transcript_field_is_rejected_without_echoing_contents(self):
        marker = "PRIVATE-SYNTHETIC-TRANSCRIPT-DO-NOT-ECHO"
        code, output = self.invoke(
            successful_evidence(raw_transcript=marker),
            "--expect-route", "quick_ai",
        )
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIn("unexpected evidence fields", output["reason"])
        self.assertNotIn(marker, json.dumps(output))

    def test_duplicate_json_fields_fail_before_route_acceptance(self):
        raw = json.dumps(successful_evidence()).replace(
            '"route": "quick_ai"',
            '"route": "deep_ai", "route": "quick_ai"',
        )
        code, output = self.invoke({}, "--expect-route", "quick_ai", raw=raw)
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIn("duplicate JSON field: route", output["reason"])

    def test_malformed_json_is_machine_readable_rejection(self):
        code, output = self.invoke({}, raw='{"outcome":')
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIsInstance(output["reason"], str)

    def test_stale_record_fails_freshness_requirement(self):
        code, output = self.invoke(
            successful_evidence(), "--max-age-seconds", "300"
        )
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIn("evidence age", output["reason"])

    def test_unexpected_success_type_does_not_pass(self):
        code, output = self.invoke(
            successful_evidence(answer_present="true"), "--require-answer"
        )
        self.assertEqual(code, 1)
        self.assertIs(output["valid"], False)
        self.assertIn("answer_present must be boolean", output["reason"])


if __name__ == "__main__":
    unittest.main()
