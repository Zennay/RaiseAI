"""Keep Watch-side schema-v2 evidence fields aligned with the Python gate.

The Watch producer is Kotlin; the acceptance validator is Python. These checks
inspect only the producer's literal JSONObject keys, so they run on hosted
Python CI without Gradle, the Watch, credentials, or a live gateway. They do
not stand in for the physical acceptance gate in issue #34.
"""

import importlib.util
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WATCH_PRODUCER = ROOT / "app/src/main/java/nl/zennay/raiseai/WatchE2eEvidence.kt"
VALIDATOR = ROOT / "tools/validate-watch-e2e-evidence.py"
SPEC = importlib.util.spec_from_file_location("watch_e2e_schema_gate", VALIDATOR)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

PUT_KEY = re.compile(r'\.put\(\s*"([^"]+)"')
ANY_PUT = re.compile(r"\.put\(\s*([^,\n)]+)")


def extract_producer_sections(source: str) -> tuple[str, str, str]:
    """Limit the scan to the three schema-producing function bodies.

    Splitting at the named declaration boundaries prevents unrelated calls in
    later Watch code from masking missing fields in a given record type.
    """
    success = source.split("fun recordSuccess(", 1)[1].split("fun recordFailure(", 1)[0]
    failure = source.split("fun recordFailure(", 1)[1].split("fun recordFailure(", 1)[0]
    common = source.split("private fun basePayload(", 1)[1].split(
        "private fun safeServerValue(", 1
    )[0]
    return common, success, failure


def field_names(section: str) -> set[str]:
    names = PUT_KEY.findall(section)
    if len(names) != len(set(names)):
        raise AssertionError("duplicate Watch JSONObject evidence field")
    # If a field name becomes dynamic, the static parity check must not
    # silently ignore it. Every evidence key needs to be auditable literally.
    for raw_argument in ANY_PUT.findall(section):
        if not re.fullmatch(r'"[^"]+"', raw_argument.strip()):
            raise AssertionError("dynamic Watch JSONObject evidence field")
    return set(names)


def producer_schemas(source: str) -> tuple[set[str], set[str]]:
    common, success, failure = extract_producer_sections(source)
    common_fields = field_names(common)
    success_fields = field_names(success)
    failure_fields = field_names(failure)
    if common_fields & success_fields or common_fields & failure_fields:
        raise AssertionError("common Watch evidence field duplicated in an outcome")
    return common_fields | success_fields, common_fields | failure_fields


class WatchE2eProducerSchemaParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WATCH_PRODUCER.read_text(encoding="utf-8")

    def test_success_and_failure_keys_match_exact_python_gate_contract(self):
        success, failure = producer_schemas(self.source)
        self.assertEqual(success, gate.SUCCESS_KEYS)
        self.assertEqual(failure, gate.FAILURE_KEYS)
        self.assertEqual(success & failure, gate.COMMON_KEYS)

    def test_common_schema_is_version_two_and_both_outcomes_use_it(self):
        common, success, failure = extract_producer_sections(self.source)
        self.assertRegex(common, r'\.put\("schema_version",\s*2\)')
        self.assertIn('basePayload("success",', success)
        self.assertIn('basePayload("failure",', failure)
        self.assertIn('BuildConfig.VERSION_NAME', common)
        self.assertIn('BuildConfig.SOURCE_REVISION', common)
        self.assertIn('Instant.now().toString()', common)

    def test_schema_mutations_do_not_pass_silently(self):
        mutations = {
            "missing_success_key": self.source.replace(
                '.put("answer_present",', '.put("answer_dropped",', 1
            ),
            "extra_success_key": self.source.replace(
                '.put("answer_present",',
                '.put("raw_answer_text", "not-safe")\n            .put("answer_present",',
                1,
            ),
            "missing_failure_key": self.source.replace(
                '.put("error_code",', '.put("error_text",', 1
            ),
            "duplicate_common_key": self.source.replace(
                '.put("latency_ms",',
                '.put("schema_version", 2)\n        .put("latency_ms",',
                1,
            ),
        }
        for name, mutated in mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(mutated, self.source, "fixture must mutate source")
                with self.assertRaises(AssertionError):
                    success, failure = producer_schemas(mutated)
                    self.assertEqual(success, gate.SUCCESS_KEYS)
                    self.assertEqual(failure, gate.FAILURE_KEYS)

    def test_accepted_keys_do_not_include_unreviewed_transcript_or_reply(self):
        success, failure = producer_schemas(self.source)
        for forbidden in {"input_text", "transcript", "answer", "response", "prompt", "message"}:
            self.assertNotIn(forbidden, success | failure)


if __name__ == "__main__":
    unittest.main()
