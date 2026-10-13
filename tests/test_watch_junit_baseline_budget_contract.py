"""Guard the original Watch JUnit regression budget against silent test loss.

Complement the repository-wide non-empty-suite check (#765): dropping four
tests from a five-test Kotlin suite should not pass merely because one remains.
The floors are explicit, reviewable snapshots, not proof of JVM execution.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

if __package__:
    from .test_kotlin_junit_discovery_presence_contract import junit_method_count
else:
    from test_kotlin_junit_discovery_presence_contract import junit_method_count


ROOT = Path(__file__).resolve().parents[1]
WATCH_TEST_DIR = "app/src/test/java/nl/zennay/raiseai"
MINIMUM_JUNIT_METHODS = {
    "AssistantModeStoreTest.kt": 5,
    "PinnedTlsTest.kt": 2,
    "RaiseGestureDetectorTest.kt": 4,
    "SensorTrialProgressTest.kt": 4,
    "VoiceRetryPolicyTest.kt": 3,
}


def junit_baseline_regressions(root: Path = ROOT) -> list[str]:
    """Report missing/corrupt/contracted canonical Kotlin Watch test suites."""
    problems: list[str] = []
    for name, minimum in sorted(MINIMUM_JUNIT_METHODS.items()):
        relative = f"{WATCH_TEST_DIR}/{name}"
        path = root / relative
        if path.is_symlink() or not path.is_file():
            problems.append(f"{relative}: missing or unsafe source")
            continue
        try:
            text = path.read_text(encoding="utf-8")
            count = junit_method_count(text)
        except (OSError, UnicodeError, ValueError) as exc:
            problems.append(f"{relative}: unreadable or malformed source ({type(exc).__name__})")
            continue
        if count < minimum:
            problems.append(
                f"{relative}: {count} real JUnit method(s), expected at least {minimum}"
            )
    return problems


def _fixture_source(number: int) -> str:
    return (
        "import org.junit.Test\n"
        "class Fixture {\n"
        + "".join(f" @Test fun scenario{index}() = Unit\n" for index in range(number))
        + "}\n"
    )


def _fixture_root(root: Path) -> Path:
    directory = root / WATCH_TEST_DIR
    directory.mkdir(parents=True)
    for name, minimum in MINIMUM_JUNIT_METHODS.items():
        (directory / name).write_text(_fixture_source(minimum), encoding="utf-8")
    return directory


class WatchJunitBaselineContract(unittest.TestCase):
    def test_real_original_watch_junit_suites_never_shrink_silently(self):
        self.assertEqual([], junit_baseline_regressions(), "baseline method counts regressed")

    def test_frozen_baseline_suites_and_budget_are_explicit(self):
        self.assertEqual(
            {
                "AssistantModeStoreTest.kt": 5,
                "PinnedTlsTest.kt": 2,
                "RaiseGestureDetectorTest.kt": 4,
                "SensorTrialProgressTest.kt": 4,
                "VoiceRetryPolicyTest.kt": 3,
            },
            MINIMUM_JUNIT_METHODS,
        )
        self.assertEqual(18, sum(MINIMUM_JUNIT_METHODS.values()))

    def test_exact_baseline_passes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_root(root)
            self.assertEqual([], junit_baseline_regressions(root))

    def test_new_tests_are_allowed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _fixture_root(root)
            suite = directory / "VoiceRetryPolicyTest.kt"
            suite.write_text(_fixture_source(7), encoding="utf-8")
            self.assertEqual([], junit_baseline_regressions(root))

    def test_partial_test_loss_is_not_hidden_by_one_remaining_test(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _fixture_root(root)
            (directory / "AssistantModeStoreTest.kt").write_text(
                _fixture_source(1), encoding="utf-8"
            )
            issues = junit_baseline_regressions(root)
            self.assertEqual(1, len(issues))
            self.assertIn("1 real JUnit method(s), expected at least 5", issues[0])

    def test_missing_original_suite_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _fixture_root(root)
            (directory / "PinnedTlsTest.kt").unlink()
            issues = junit_baseline_regressions(root)
            self.assertEqual(1, len(issues))
            self.assertIn("missing or unsafe source", issues[0])

    def test_symlink_replacing_original_test_suite_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _fixture_root(root)
            suite = directory / "PinnedTlsTest.kt"
            suite.unlink()
            suite.symlink_to(directory / "VoiceRetryPolicyTest.kt")
            issues = junit_baseline_regressions(root)
            self.assertEqual(1, len(issues))
            self.assertIn("missing or unsafe source", issues[0])

    def test_comments_and_strings_cannot_restore_removed_coverage(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _fixture_root(root)
            (directory / "SensorTrialProgressTest.kt").write_text(
                'import org.junit.Test\n'
                'class Fixture {\n'
                ' @Test fun onlyReal() = Unit\n'
                ' val fake = """@Test fun hidden() = Unit"""\n'
                ' /* @Test fun fakeComment() = Unit */\n'
                '}\n',
                encoding="utf-8",
            )
            issues = junit_baseline_regressions(root)
            self.assertEqual(1, len(issues))
            self.assertIn("1 real JUnit method(s), expected at least 4", issues[0])

    def test_invalid_unicode_and_unterminated_literals_fail_closed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _fixture_root(root)
            suite = directory / "RaiseGestureDetectorTest.kt"
            suite.write_bytes(b"\xff")
            self.assertIn("UnicodeDecodeError", junit_baseline_regressions(root)[0])
            suite.write_text('val bad = """unfinished', encoding="utf-8")
            self.assertIn("ValueError", junit_baseline_regressions(root)[0])

    def test_an_additional_valid_suite_does_not_reduce_existing_budget(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _fixture_root(root)
            (directory / "AdditionalWatchTest.kt").write_text(
                _fixture_source(6), encoding="utf-8"
            )
            self.assertEqual([], junit_baseline_regressions(root))


if __name__ == "__main__":
    unittest.main()
