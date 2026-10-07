from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
FROZEN_SOURCE_REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
FROZEN_RELEASE_TAG = "physical-handoff-v1.5.2-8f719bb"
FROZEN_RELEASE_ASSET_ID = "611084738"
FROZEN_ARCHIVE_SHA256 = "867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce"

def read_contract_text(path: Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"{path.name}: documentation input must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path.name}: documentation input must be a regular file")
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}: documentation input must be valid UTF-8") from exc


PHYSICAL_ACCEPTANCE_ENTRYPOINTS = (
    "start-frozen-acceptance.command",
    "start-physical-handoff.command",
    "tools/fetch-frozen-physical-handoff.py",
    "tools/create-physical-observation-template.py",
    "tools/validate-physical-observations.py",
)


class ReleaseDocumentationIdentityContractTests(unittest.TestCase):
    def test_documentation_reader_rejects_symlink_nonregular_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            regular = root / "regular.md"
            regular.write_text("# Raise\n", encoding="utf-8")
            linked = root / "linked.md"
            linked.symlink_to(regular)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                read_contract_text(linked)

            directory = root / "directory.md"
            directory.mkdir()
            with self.assertRaisesRegex(ValueError, "must be a regular file"):
                read_contract_text(directory)

            invalid = root / "invalid.md"
            invalid.write_bytes(b"# Raise\xff")
            with self.assertRaisesRegex(ValueError, "must be valid UTF-8"):
                read_contract_text(invalid)

    def test_version_file_is_canonical_single_line_utf8(self):
        text = read_contract_text(ROOT / "VERSION.txt")
        self.assertIsNotNone(
            re.fullmatch(r"\d+\.\d+\.\d+\n", text),
            "VERSION.txt must contain exactly one canonical SemVer line terminated by LF",
        )

    def test_repository_version_matches_android_version_name(self):
        version = read_contract_text(ROOT / "VERSION.txt").strip()
        self.assertRegex(version, VERSION_RE)

        build_text = read_contract_text(ROOT / "app" / "build.gradle.kts")
        version_names = re.findall(
            r'(?m)^\s*versionName\s*=\s*"([^"]+)"\s*$',
            build_text,
        )
        self.assertEqual(
            version_names,
            [version],
            "Android versionName must exactly match the canonical repository VERSION.txt",
        )

    def test_readme_tracks_repository_version(self):
        version = read_contract_text(ROOT / "VERSION.txt").strip()
        self.assertRegex(version, VERSION_RE)

        first_line = read_contract_text(ROOT / "README.md").splitlines()[0]
        self.assertEqual(first_line, f"# Raise AI v{version} — Galaxy Watch 7")

    def test_readme_next_gate_pins_exact_preserved_carrier_identity(self):
        text = read_contract_text(ROOT / "README.md")
        self.assertEqual(text.count("## Next proof gate\n"), 1)
        next_gate = text.split("## Next proof gate\n", 1)[1].split("\n## ", 1)[0]
        required = (
            f"merged-main revision `{FROZEN_SOURCE_REVISION}`",
            f"GitHub Release tag `{FROZEN_RELEASE_TAG}`",
            f"Release asset id `{FROZEN_RELEASE_ASSET_ID}`",
            f"archive digest `sha256:{FROZEN_ARCHIVE_SHA256}`",
            "Any different carrier or rebuilt APK is not acceptance evidence.",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertEqual(
                    next_gate.count(marker),
                    1,
                    "README next proof gate must bind the frozen carrier unambiguously",
                )

    def test_start_here_distinguishes_tip_from_frozen_acceptance(self):
        text = read_contract_text(ROOT / "START-HERE.md")
        self.assertTrue(
            text.startswith("# Raise AI — START HERE (frozen v1.5.2 acceptance)\n"),
            "START-HERE must identify itself as the frozen acceptance guide, not the repository-tip release",
        )
        required = (
            "The only valid acceptance input is the preserved v1.5.2 handoff",
            FROZEN_SOURCE_REVISION,
            "do not build from the repository tip",
            "Do not run `physical-validation.command all` from the current checkout",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_start_here_pins_exact_preserved_carrier_identity(self):
        text = read_contract_text(ROOT / "START-HERE.md")
        required = (
            f"merged-main revision `{FROZEN_SOURCE_REVISION}`",
            f"GitHub Release tag `{FROZEN_RELEASE_TAG}`",
            f"Release asset id `{FROZEN_RELEASE_ASSET_ID}`",
            f"archive digest `sha256:{FROZEN_ARCHIVE_SHA256}`",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertEqual(
                    text.count(marker),
                    1,
                    "START-HERE must bind the frozen acceptance carrier unambiguously",
                )

    def test_operator_guides_pin_the_same_frozen_carrier(self):
        guides = {
            "START-HERE.md": read_contract_text(ROOT / "START-HERE.md"),
            "PHYSICAL-ACCEPTANCE.md": read_contract_text(ROOT / "PHYSICAL-ACCEPTANCE.md"),
            "DEVICE-TEST.md": read_contract_text(ROOT / "DEVICE-TEST.md"),
        }
        markers = (
            FROZEN_SOURCE_REVISION,
            FROZEN_RELEASE_TAG,
            FROZEN_RELEASE_ASSET_ID,
            FROZEN_ARCHIVE_SHA256,
        )
        for guide, text in guides.items():
            for marker in markers:
                with self.subTest(guide=guide, marker=marker):
                    self.assertIn(
                        marker,
                        text,
                        f"{guide} must retain the canonical frozen carrier identity",
                    )

    def test_historical_device_checklist_cannot_masquerade_as_acceptance(self):
        text = read_contract_text(ROOT / "DEVICE-TEST.md")
        required = (
            "**Historical fallback checklist only.**",
            "Do not use this V0.3 Gemini-first checklist for the current physical acceptance gate.",
            "The only valid acceptance carrier is the preserved Raise AI v1.5.2 handoff",
            "bash ./start-frozen-acceptance.command [gateway-profile]",
            "Any different carrier or rebuilt APK is not acceptance evidence.",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertEqual(
                    text.count(marker),
                    1,
                    "legacy checklist must fail closed toward the canonical frozen acceptance path",
                )

    def test_legacy_fallback_guides_redirect_without_partial_carrier_identity(self):
        guides = {
            "REMOTE-LOGIN.md": read_contract_text(ROOT / "REMOTE-LOGIN.md"),
            "GEMINI-HOME-SETUP.md": read_contract_text(ROOT / "GEMINI-HOME-SETUP.md"),
            "CHATGPT-WEB-SETUP.md": read_contract_text(ROOT / "CHATGPT-WEB-SETUP.md"),
        }
        required = (
            "GitHub issue #34",
            "bash ./start-frozen-acceptance.command [gateway-profile]",
            "START-HERE.md",
        )
        forbidden = (
            FROZEN_SOURCE_REVISION,
            FROZEN_RELEASE_TAG,
            FROZEN_RELEASE_ASSET_ID,
            FROZEN_ARCHIVE_SHA256,
        )
        for guide, text in guides.items():
            for marker in required:
                with self.subTest(guide=guide, required=marker):
                    self.assertIn(
                        marker,
                        text,
                        f"{guide} must redirect operators to the canonical frozen acceptance path",
                    )
            for marker in forbidden:
                with self.subTest(guide=guide, forbidden=marker):
                    self.assertNotIn(
                        marker,
                        text,
                        f"{guide} must not duplicate a partial frozen carrier identity; START-HERE.md is canonical",
                    )

    def test_frozen_acceptance_version_is_not_derived_from_version_txt(self):
        current_version = read_contract_text(ROOT / "VERSION.txt").strip()
        self.assertNotEqual(
            current_version,
            "1.5.2",
            "This regression is useful only while repository tip differs from the frozen v1.5.2 acceptance input",
        )


    def test_physical_acceptance_observation_template_command_uses_real_bash_continuation(self):
        text = read_contract_text(ROOT / "PHYSICAL-ACCEPTANCE.md")
        lines = text.splitlines()
        command = "python3 tools/create-physical-observation-template.py " + "\\"

        self.assertEqual(
            lines.count(command),
            1,
            "physical runbook must contain one canonical observation-template command",
        )
        command_index = lines.index(command)
        self.assertEqual(
            lines[command_index + 1],
            "  ~/.raiseai/evidence/<session>/session.json",
            "session.json must remain the continued argument to the generator command",
        )
        self.assertNotIn(
            command + "\\",
            lines,
            "two trailing backslashes break Bash line continuation and must fail the documentation contract",
        )


    def test_physical_acceptance_entrypoints_are_tracked_regular_files(self):
        text = read_contract_text(ROOT / "PHYSICAL-ACCEPTANCE.md")
        tracked = {
            item
            for item in subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
            .decode("utf-8")
            .split("\0")
            if item
        }

        for relative in PHYSICAL_ACCEPTANCE_ENTRYPOINTS:
            with self.subTest(relative=relative):
                self.assertIn(
                    relative,
                    text,
                    f"physical runbook must reference canonical entrypoint {relative}",
                )
                self.assertIn(
                    relative,
                    tracked,
                    f"physical runbook entrypoint must remain tracked: {relative}",
                )
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"physical runbook entrypoint must not be a symlink: {relative}",
                )
                self.assertTrue(
                    path.is_file(),
                    f"physical runbook entrypoint must remain a regular file: {relative}",
                )


    def test_physical_acceptance_validator_persists_secret_safe_quality_result(self):
        text = read_contract_text(ROOT / "PHYSICAL-ACCEPTANCE.md")
        command = "\n".join(
            (
                "python3 tools/validate-physical-observations.py " + "\\",
                "  ~/.raiseai/evidence/<session>/session.json " + "\\",
                "  ~/.raiseai/evidence/<session>/operator-observations.json " + "\\",
                "  --output ~/.raiseai/evidence/<session>/quality-result.json",
            )
        )
        self.assertEqual(
            text.count(command),
            1,
            "physical runbook must persist the secret-safe quality-result.json output",
        )


    def test_physical_acceptance_default_share_set_excludes_raw_identity_and_notes(self):
        text = read_contract_text(ROOT / "PHYSICAL-ACCEPTANCE.md")
        share_section = text.split("Default GitHub issue #34 share set:\n", 1)[1].split(
            "\nAttach or link only the reviewed safe evidence", 1
        )[0]
        self.assertEqual(
            share_section.count("- `e2e-result.json`"),
            1,
            "E2E summary must be in the default share set",
        )
        self.assertEqual(
            share_section.count("- `v1-result.json`"),
            1,
            "V1 summary must be in the default share set",
        )
        self.assertEqual(
            share_section.count("- `quality-result.json`"),
            1,
            "quality summary must be in the default share set",
        )
        for local_only in (
            "session.json",
            "operator-observations.json",
            "raw diagnostics directories",
            "raw trace/trial CSV files",
        ):
            with self.subTest(local_only=local_only):
                self.assertIn(local_only, share_section)
        self.assertIn(
            "session.json` contains the Watch serial and is not part of the default share set",
            share_section,
        )


if __name__ == "__main__":
    unittest.main()
