import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-tooling-test.yml"

EXPECTED_STEP_KEYS = {
    "Checkout exact tested revision": ["name", "uses", "with"],
    "Verify exact tested revision": ["name", "shell", "env", "run"],
    "Verify Python runtime": ["name", "shell", "run"],
    "Shell syntax": ["name", "shell", "run"],
    "Python syntax": ["name", "shell", "run"],
    "Quality tooling regressions": ["name", "shell", "run"],
}


class QualityToolingStepSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.lines = WORKFLOW.read_text(encoding="utf-8").splitlines()

    def _steps(self):
        starts = [
            index
            for index, line in enumerate(self.lines)
            if line.startswith("      - name:")
        ]
        self.assertTrue(starts, "quality workflow must contain named steps")

        steps = []
        for offset, start in enumerate(starts):
            end = starts[offset + 1] if offset + 1 < len(starts) else len(self.lines)
            block = self.lines[start:end]
            name = block[0].split(":", 1)[1].strip()
            steps.append((name, block))
        return steps

    @staticmethod
    def _top_level_step_keys(block):
        keys = []
        for line in block:
            match = re.fullmatch(r"      - ([A-Za-z0-9_-]+):(?:.*)", line)
            if match:
                keys.append(match.group(1))
                continue
            match = re.fullmatch(r"        ([A-Za-z0-9_-]+):(?:.*)", line)
            if match:
                keys.append(match.group(1))
        return keys

    def test_step_names_and_order_are_exact(self):
        self.assertEqual(
            [name for name, _ in self._steps()],
            list(EXPECTED_STEP_KEYS),
            "hosted quality workflow must not gain, remove, rename, or reorder execution steps",
        )

    def test_each_step_has_only_audited_top_level_keys(self):
        for name, block in self._steps():
            with self.subTest(step=name):
                self.assertEqual(
                    self._top_level_step_keys(block),
                    EXPECTED_STEP_KEYS[name],
                    f"{name!r} must not gain unreviewed step-level execution controls",
                )

    def test_execution_mode_is_locked_per_step(self):
        for name, block in self._steps():
            text = "\n".join(block)
            with self.subTest(step=name):
                if name == "Checkout exact tested revision":
                    self.assertIn("        uses: actions/checkout@", text)
                    self.assertNotRegex(text, r"(?m)^        run:")
                else:
                    self.assertIn("        shell: bash", text)
                    self.assertIn("        run: |", text)
                    self.assertNotRegex(text, r"(?m)^        uses:")

    def test_only_revision_verifier_has_step_environment(self):
        env_steps = [
            name
            for name, block in self._steps()
            if any(line == "        env:" for line in block)
        ]
        self.assertEqual(
            env_steps,
            ["Verify exact tested revision"],
            "step-scoped environment must remain limited to exact-head verification",
        )


if __name__ == "__main__":
    unittest.main()
