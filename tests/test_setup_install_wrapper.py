import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SetupInstallWrapperTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.outside = self.root / "outside"
        self.outside.mkdir()
        self.trace = self.root / "upgrade-trace"

        self.wrapper = self.repo / "setup-and-install-watch.command"
        shutil.copy2(ROOT / "setup-and-install-watch.command", self.wrapper)
        self.wrapper.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def write_upgrade(self, body):
        upgrade = self.repo / "upgrade-watch.command"
        upgrade.write_text(
            "#!/bin/bash\nset -euo pipefail\n" + textwrap.dedent(body),
            encoding="utf-8",
        )
        upgrade.chmod(0o755)

    def run_wrapper(self, *args):
        env = os.environ.copy()
        env["TRACE_FILE"] = str(self.trace)
        return subprocess.run(
            [str(self.wrapper), *args],
            cwd=self.outside,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def test_delegates_to_sibling_from_repository_directory_and_preserves_exit(self):
        self.write_upgrade(
            """
            printf '%s\n' "$PWD" > "$TRACE_FILE"
            exit 23
            """
        )

        result = self.run_wrapper()

        self.assertEqual(result.returncode, 23, result.stdout)
        self.assertEqual(
            self.trace.read_text(encoding="utf-8").strip(),
            str(self.repo),
        )
        self.assertIn("Raise AI first-time setup/install", result.stdout)
        self.assertNotIn("Race AI", result.stdout)

    def test_rejects_unexpected_arguments_before_upgrade(self):
        self.write_upgrade(
            """
            printf 'invoked\n' > "$TRACE_FILE"
            exit 0
            """
        )

        result = self.run_wrapper("unexpected")

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage: ./setup-and-install-watch.command", result.stdout)
        self.assertFalse(self.trace.exists())


if __name__ == "__main__":
    unittest.main()
