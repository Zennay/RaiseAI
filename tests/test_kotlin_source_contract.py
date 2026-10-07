import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "kotlin-source-contract.yml"
EXPECTED_CRITICAL = {
    "build.gradle.kts",
    "settings.gradle.kts",
    "app/build.gradle.kts",
    "app/src/main/java/nl/zennay/raiseai/GatewayClient.kt",
    "app/src/main/java/nl/zennay/raiseai/MainActivity.kt",
    "app/src/main/java/nl/zennay/raiseai/WatchE2eEvidence.kt",
}
UTF8_BOM = b"\xef\xbb\xbf"


def tracked_kotlin_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix.lower() in {".kt", ".kts"}
    )


def decode_strict_utf8(data: bytes, *, label: str) -> str:
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be strict UTF-8") from exc


def validate_kotlin_source(data: bytes, *, label: str) -> str:
    if data.startswith(UTF8_BOM):
        raise ValueError(f"{label} must not start with a UTF-8 BOM")

    text = decode_strict_utf8(data, label=label)
    if "\x00" in text:
        raise ValueError(f"{label} must not contain NUL bytes")
    if "\r" in text:
        raise ValueError(f"{label} must use LF-only line endings")
    return text


class KotlinSourceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_kotlin_surface_is_nonempty_and_includes_critical_files(self):
        paths = tracked_kotlin_paths()
        self.assertTrue(paths, "tracked Kotlin discovery must find files")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical Kotlin/Gradle Kotlin files missing from discovery: "
            f"{sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_kotlin_file_is_regular_canonical_utf8_text(self):
        for relative in tracked_kotlin_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                self.assertTrue(path.is_file(), f"{relative} must resolve to a regular file")
                validate_kotlin_source(path.read_bytes(), label=relative)

    def test_strict_decoder_rejects_malformed_utf8(self):
        with self.assertRaisesRegex(ValueError, "fixture.kt must be strict UTF-8"):
            decode_strict_utf8(b"fun main() {\xff}\n", label="fixture.kt")

    def test_validator_rejects_utf8_bom(self):
        with self.assertRaisesRegex(ValueError, "must not start with a UTF-8 BOM"):
            validate_kotlin_source(UTF8_BOM + b"fun main() {}\n", label="fixture.kt")

    def test_validator_rejects_cr_line_endings(self):
        for payload in (b"fun main() {}\r\n", b"fun main() {}\r"):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "must use LF-only line endings"):
                    validate_kotlin_source(payload, label="fixture.kt")

    def test_validator_rejects_nul_bytes(self):
        with self.assertRaisesRegex(ValueError, "must not contain NUL bytes"):
            validate_kotlin_source(b"fun main() {}\x00\n", label="fixture.kt")

    def _trigger_paths(self, event: str) -> list[str]:
        lines = self.workflow.splitlines()
        start = lines.index(f"  {event}:") + 1
        body = []
        for line in lines[start:]:
            if line and not line.startswith("    "):
                break
            body.append(line)
        self.assertIn("    paths:", body)
        index = body.index("    paths:") + 1
        paths = []
        for line in body[index:]:
            match = re.fullmatch(r'      - "([^"]+)"', line)
            if not match:
                break
            paths.append(match.group(1))
        return paths

    def test_workflow_triggers_cover_current_and_future_kotlin_surfaces(self):
        expected = [
            "*.kt",
            "**/*.kt",
            "*.kts",
            "**/*.kts",
            "tests/test_kotlin_source_contract.py",
            ".github/workflows/kotlin-source-contract.yml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._trigger_paths(event), expected)

    def test_workflow_keeps_exact_top_level_job_trigger_and_env_surfaces(self):
        lines = self.workflow.splitlines()

        top_level = [
            match.group(1)
            for line in lines
            if (match := re.fullmatch(r"([A-Za-z0-9_-]+):.*", line))
        ]
        self.assertEqual(top_level, ["name", "on", "permissions", "concurrency", "jobs"])
        self.assertEqual(lines[0], "name: Kotlin source contract CI")

        jobs_block = self.workflow.split("\njobs:\n", 1)[1]
        job_keys = [
            match.group(1)
            for line in jobs_block.splitlines()[1:]
            if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line))
        ]
        self.assertEqual(job_keys, ["runs-on", "timeout-minutes", "env", "steps"])

        on_start = lines.index("on:") + 1
        permissions_start = lines.index("permissions:")
        events = [
            match.group(1)
            for line in lines[on_start:permissions_start]
            if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(events, ["push", "pull_request"])

        def event_block(event):
            start = lines.index(f"  {event}:") + 1
            block = []
            for line in lines[start:]:
                if line and not line.startswith("    "):
                    break
                block.append(line)
            return block

        push = event_block("push")
        self.assertEqual(
            [
                match.group(1)
                for line in push
                if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
            ],
            ["branches", "paths"],
        )
        branches_start = push.index("    branches:") + 1
        self.assertEqual(push[branches_start], "      - main")

        pull_request = event_block("pull_request")
        self.assertEqual(
            [
                match.group(1)
                for line in pull_request
                if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
            ],
            ["paths"],
            "pull_request must not gain filters that can skip synchronize validation",
        )

        concurrency_start = lines.index("concurrency:") + 1
        jobs_start = lines.index("jobs:")
        self.assertEqual(
            [
                match.group(1)
                for line in lines[concurrency_start:jobs_start]
                if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):.*", line))
            ],
            ["group", "cancel-in-progress"],
        )

        env_start = lines.index("    env:") + 1
        env_keys = []
        for line in lines[env_start:]:
            match = re.fullmatch(r"      ([A-Za-z0-9_-]+):.*", line)
            if match:
                env_keys.append(match.group(1))
                continue
            break
        self.assertEqual(
            env_keys,
            [
                "LANG",
                "LC_ALL",
                "PYTHONHASHSEED",
                "PYTHONNOUSERSITE",
                "PYTHONDONTWRITEBYTECODE",
                "TZ",
            ],
        )

    def test_workflow_step_and_nested_mapping_surfaces_are_exact(self):
        lines = self.workflow.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        expected_names = [
            "Checkout exact tested revision",
            "Verify exact tested revision",
            "Verify Python runtime",
            "Validate Kotlin source contract",
            "Verify worktree remains clean",
        ]
        names = [lines[index].removeprefix("      - name: ") for index in step_starts]
        self.assertEqual(names, expected_names, "Kotlin workflow must not gain unreviewed steps")

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Validate Kotlin source contract": ["name", "shell", "run"],
            "Verify worktree remains clean": ["name", "shell", "run"],
        }
        for position, start in enumerate(step_starts):
            end = step_starts[position + 1] if position + 1 < len(step_starts) else len(lines)
            step = lines[start:end]
            name = names[position]
            keys = ["name"]
            for line in step[1:]:
                match = re.fullmatch(r"        ([A-Za-z0-9_-]+):.*", line)
                if match:
                    keys.append(match.group(1))
            self.assertEqual(keys, expected_keys[name])

        def step_named(name):
            start = lines.index(f"      - name: {name}")
            following = [
                index
                for index, line in enumerate(lines)
                if index > start and line.startswith("      - name:")
            ]
            end = min(following) if following else len(lines)
            return lines[start:end]

        checkout = step_named("Checkout exact tested revision")
        checkout_keys = []
        with_start = checkout.index("        with:") + 1
        for line in checkout[with_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                checkout_keys.append(match.group(1))
                continue
            break
        self.assertEqual(checkout_keys, ["ref", "persist-credentials"])

        verifier = step_named("Verify exact tested revision")
        verifier_keys = []
        env_start = verifier.index("        env:") + 1
        for line in verifier[env_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                verifier_keys.append(match.group(1))
                continue
            break
        self.assertEqual(verifier_keys, ["EXPECTED_SHA"])

    def test_workflow_is_hosted_read_only_exact_head_bounded_and_strict(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertNotIn("self-hosted", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotRegex(self.workflow, r"\$\{\{\s*secrets\.")
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("continue-on-error: true", self.workflow)
        self.assertIn("timeout-minutes: 5", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)

        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        expression = expression.replace("\\$", "$")
        self.assertEqual(self.workflow.count(expression), 2)
        self.assertIn("persist-credentials: false", self.workflow)

        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.workflow,
            flags=re.MULTILINE,
        )
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")

        lines = self.workflow.splitlines()
        run_indices = [index for index, line in enumerate(lines) if line == "        run: |"]
        self.assertTrue(run_indices)
        step_starts = [
            index for index, line in enumerate(lines) if line.startswith("      - name:")
        ]
        for run_index in run_indices:
            step_start = max(index for index in step_starts if index < run_index)
            following = [index for index in step_starts if index > step_start]
            step_end = min(following) if following else len(lines)
            step = lines[step_start:step_end]
            self.assertIn("        shell: bash", step)
            self.assertEqual(lines[run_index + 1], "          set -euo pipefail")



if __name__ == "__main__":
    unittest.main()
