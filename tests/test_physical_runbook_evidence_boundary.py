"""Guard the operator runbook's boundary between private and shareable Watch evidence.

This is a documentation contract, not a substitute for physical device testing.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "PHYSICAL-ACCEPTANCE.md"
SHAREABLE = ("e2e-result.json", "v1-result.json", "quality-result.json")
PRIVATE = ("session.json", "operator-observations.json")


def share_section(markdown: str) -> str:
    marker = "Default GitHub issue #34 share set:"
    if markdown.count(marker) != 1:
        raise ValueError("Exactly one default share-set heading is required")
    remainder = markdown.split(marker, 1)[1]
    return remainder.split("\n## ", 1)[0]


def bullet_list_after_heading(section: str) -> list[str]:
    lines = section.splitlines()
    items = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:])
        elif items and stripped:
            break
    return items


class PhysicalRunbookEvidenceBoundaryTests(unittest.TestCase):
    def test_only_three_public_summaries_are_offered_by_default(self):
        section = share_section(RUNBOOK.read_text(encoding="utf-8"))
        items = bullet_list_after_heading(section)
        self.assertEqual(items, [f"`{name}`" for name in SHAREABLE])

    def test_raw_private_evidence_is_explicitly_local(self):
        section = share_section(RUNBOOK.read_text(encoding="utf-8"))
        self.assertIn("Keep `session.json`", section)
        self.assertIn("`operator-observations.json`", section)
        self.assertIn("local", section)
        self.assertIn("raw trace/trial CSV", section)

    def test_frozen_build_cannot_be_replaced_by_repo_tip(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("Do not substitute a newer APK", text)
        self.assertIn("8f719bb273f9b997848864f342598e7df5f090e5", text)
        self.assertIn("37241768528", text)

    def test_regression_rejects_extraneous_share_item(self):
        original = RUNBOOK.read_text(encoding="utf-8")
        mutated = original.replace(
            "- `quality-result.json`\n\nKeep `session.json`",
            "- `quality-result.json`\n- `session.json`\n\nKeep `session.json`",
            1,
        )
        self.assertNotEqual(original, mutated, "mutation fixture must match runbook")
        self.assertNotEqual(
            bullet_list_after_heading(share_section(mutated)),
            [f"`{name}`" for name in SHAREABLE],
        )


if __name__ == "__main__":
    unittest.main()
