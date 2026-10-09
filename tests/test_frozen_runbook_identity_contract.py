"""Regression guard: physical runbook must retain the exact frozen Watch identity.

This test intentionally does not inspect or execute the physical APK.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "PHYSICAL-ACCEPTANCE.md"

EXPECTED = {
    "source revision": "8f719bb273f9b997848864f342598e7df5f090e5",
    "GitHub Actions run": "37241768528",
    "artifact": "RaiseAI-Watch7-v1.5.2-physical-handoff-37241768528",
    "artifact id": "11317304352",
    "artifact digest": "sha256:867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce",
}


def check_frozen_identity(markdown: str) -> None:
    heading = "# Physical V1 acceptance — frozen v1.5.2 handoff"
    if not markdown.startswith(heading + "\n"):
        raise ValueError("physical runbook no longer begins with frozen v1.5.2 heading")
    section = re.search(
        r"(?m)^## Frozen acceptance input\s*$([\s\S]*?)(?=^## |\Z)",
        markdown,
    )
    if section is None:
        raise ValueError("frozen acceptance section missing")
    body = section.group(1)
    for label, value in EXPECTED.items():
        pattern = rf"(?m)^- {re.escape(label)}: `{re.escape(value)}`\s*$"
        if len(re.findall(pattern, body)) != 1:
            raise ValueError(f"frozen identity missing, duplicated or changed: {label}")
    if "Do not substitute a newer APK" not in body:
        raise ValueError("frozen APK substitution prohibition missing")


class FrozenRunbookIdentityContract(unittest.TestCase):
    def test_current_runbook(self):
        check_frozen_identity(RUNBOOK.read_text(encoding="utf-8"))

    def test_changed_source_revision_rejected(self):
        original = RUNBOOK.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source revision"):
            check_frozen_identity(original.replace(EXPECTED["source revision"], "0" * 40, 1))

    def test_duplicated_artifact_id_rejected(self):
        original = RUNBOOK.read_text(encoding="utf-8")
        duplicate = f"- artifact id: `{EXPECTED['artifact id']}`\n"
        with self.assertRaisesRegex(ValueError, "artifact id"):
            check_frozen_identity(original.replace(duplicate, duplicate * 2, 1))

    def test_missing_no_substitution_warning_rejected(self):
        original = RUNBOOK.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "substitution"):
            check_frozen_identity(original.replace("Do not substitute a newer APK", "New APKs are acceptable", 1))

    def test_changed_heading_rejected(self):
        original = RUNBOOK.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "heading"):
            check_frozen_identity(original.replace("frozen v1.5.2 handoff", "latest available APK", 1))


if __name__ == "__main__":
    unittest.main()
