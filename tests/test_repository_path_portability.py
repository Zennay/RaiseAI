import os
import pathlib
import subprocess
import tempfile
import unicodedata
import unittest


WINDOWS_RESERVED_BASENAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
    *(f"com{digit}" for digit in "¹²³"),
    *(f"lpt{digit}" for digit in "¹²³"),
}
WINDOWS_FORBIDDEN_CHARACTERS = set('<>:"\\|?*')
ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWED_EXECUTABLE_SHEBANGS = {
    "#!/bin/bash",
    "#!/usr/bin/env bash",
    "#!/usr/bin/env node",
    "#!/usr/bin/env python3",
}


def tracked_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("tracked repository paths must be strict UTF-8") from exc
    return [item for item in decoded.split("\0") if item]


def tracked_index_entries() -> list[tuple[str, str, str]]:
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
    entries: list[tuple[str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, _object_id, stage = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("tracked index entry must have canonical Git stage metadata") from exc
        entries.append((mode, stage, path))
    return entries


def validate_regular_file_entries(entries: list[tuple[str, str, str]]) -> None:
    if not entries:
        raise ValueError("repository index discovery must not be empty")

    for mode, stage, path in entries:
        if stage != "0":
            raise ValueError(f"{path!r}: unmerged Git index stage {stage} is forbidden")
        if mode not in {"100644", "100755"}:
            raise ValueError(
                f"{path!r}: tracked entry mode {mode} is not a regular file"
            )


def validate_executable_entry_sources(
    entries: list[tuple[str, str, str]],
    *,
    root: pathlib.Path = ROOT,
) -> None:
    for mode, stage, path in entries:
        if mode != "100755":
            continue
        if stage != "0":
            raise ValueError(f"{path!r}: executable entry must be at canonical stage 0")

        candidate = root / path
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"{path!r}: executable entry must be a regular file")

        with candidate.open("rb") as source:
            first_line = source.readline(257)
        if len(first_line) > 256 and not first_line.endswith(b"\n"):
            raise ValueError(f"{path!r}: executable shebang is unreasonably long")
        try:
            shebang = first_line.removesuffix(b"\n").decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{path!r}: executable shebang must be strict UTF-8") from exc

        if shebang not in ALLOWED_EXECUTABLE_SHEBANGS:
            raise ValueError(
                f"{path!r}: executable entry must declare a reviewed interpreter"
            )


def validate_portable_paths(paths: list[str]) -> None:
    if not paths:
        raise ValueError("repository path discovery must not be empty")

    seen: dict[str, str] = {}
    for path in paths:
        if unicodedata.normalize("NFC", path) != path:
            raise ValueError(f"{path!r}: repository path must already be NFC-normalized")

        segments = path.split("/")
        if not all(segments):
            raise ValueError(f"{path!r}: repository path must not contain empty segments")

        for segment in segments:
            if segment in {".", ".."}:
                raise ValueError(f"{path!r}: dot path segments are forbidden")
            if segment.endswith((" ", ".")):
                raise ValueError(
                    f"{path!r}: path segments must not end in a space or period"
                )
            if any(ord(char) < 32 for char in segment):
                raise ValueError(f"{path!r}: ASCII control characters are forbidden")
            if any(unicodedata.category(char) in {"Cc", "Cf"} for char in segment):
                raise ValueError(
                    f"{path!r}: Unicode control and format characters are forbidden"
                )
            if any(unicodedata.category(char) in {"Zl", "Zp"} for char in segment):
                raise ValueError(
                    f"{path!r}: Unicode line and paragraph separators are forbidden"
                )
            if any(char in WINDOWS_FORBIDDEN_CHARACTERS for char in segment):
                raise ValueError(
                    f"{path!r}: Windows-reserved filename characters are forbidden"
                )

            basename = segment.split(".", 1)[0].casefold()
            if basename in WINDOWS_RESERVED_BASENAMES:
                raise ValueError(
                    f"{path!r}: Windows-reserved basename {basename!r} is forbidden"
                )

        portable_key = unicodedata.normalize("NFC", path).casefold()
        previous = seen.get(portable_key)
        if previous is not None:
            raise ValueError(
                f"portable repository path collision: {previous!r} vs {path!r}"
            )
        seen[portable_key] = path


class RepositoryPathPortabilityTests(unittest.TestCase):
    def test_every_tracked_path_is_portable_and_collision_free(self):
        paths = tracked_paths()
        self.assertTrue(paths)
        validate_portable_paths(paths)

    def test_every_tracked_entry_is_a_merged_regular_file(self):
        entries = tracked_index_entries()
        self.assertTrue(entries)
        validate_regular_file_entries(entries)
        validate_executable_entry_sources(entries)
        self.assertEqual(
            [path for _mode, _stage, path in entries],
            tracked_paths(),
            "stage metadata and tracked-path discovery must describe the same ordered surface",
        )

    def test_git_discovery_is_bound_to_repository_root(self):
        original_cwd = pathlib.Path.cwd()
        with tempfile.TemporaryDirectory(prefix="raiseai-portability-cwd-") as temporary:
            try:
                os.chdir(temporary)
                paths = tracked_paths()
                entries = tracked_index_entries()
            finally:
                os.chdir(original_cwd)

        self.assertIn("tests/test_repository_path_portability.py", paths)
        self.assertEqual(
            [path for _mode, _stage, path in entries],
            paths,
            "repository discovery must not depend on the caller's working directory",
        )

    def test_accepts_regular_file_modes(self):
        validate_regular_file_entries(
            [
                ("100644", "0", "README.md"),
                ("100755", "0", "gradlew"),
            ]
        )

    def test_rejects_symlink_gitlink_and_nonregular_modes(self):
        for mode in ("120000", "160000", "100664"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError, "not a regular file"):
                    validate_regular_file_entries([(mode, "0", "fixture")])

    def test_rejects_unmerged_index_stages(self):
        for stage in ("1", "2", "3"):
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(ValueError, "unmerged Git index stage"):
                    validate_regular_file_entries([("100644", stage, "fixture")])

    def test_rejects_empty_index_surface(self):
        with self.assertRaisesRegex(ValueError, "index discovery must not be empty"):
            validate_regular_file_entries([])

    def test_executable_entries_require_reviewed_shebangs(self):
        with tempfile.TemporaryDirectory(prefix="raiseai-executable-") as temporary:
            root = pathlib.Path(temporary)
            fixtures = {
                "bash.sh": "#!/usr/bin/env bash\necho ok\n",
                "wrapper": "#!/bin/bash\necho ok\n",
                "tool.py": "#!/usr/bin/env python3\nprint('ok')\n",
                "smoke.mjs": "#!/usr/bin/env node\nconsole.log('ok')\n",
            }
            entries = []
            for name, source in fixtures.items():
                (root / name).write_text(source, encoding="utf-8")
                entries.append(("100755", "0", name))

            validate_executable_entry_sources(entries, root=root)

    def test_nonexecutable_entries_do_not_require_shebangs(self):
        with tempfile.TemporaryDirectory(prefix="raiseai-executable-") as temporary:
            root = pathlib.Path(temporary)
            (root / "README.md").write_text("# docs\n", encoding="utf-8")
            validate_executable_entry_sources(
                [("100644", "0", "README.md")],
                root=root,
            )

    def test_rejects_executable_without_reviewed_interpreter(self):
        with tempfile.TemporaryDirectory(prefix="raiseai-executable-") as temporary:
            root = pathlib.Path(temporary)
            fixtures = {
                "missing.txt": "plain text\n",
                "unsupported.py": "#!/usr/bin/python3\nprint('no')\n",
            }
            for name, source in fixtures.items():
                with self.subTest(name=name):
                    (root / name).write_text(source, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "reviewed interpreter"):
                        validate_executable_entry_sources(
                            [("100755", "0", name)],
                            root=root,
                        )

    def test_accepts_normal_cross_platform_paths(self):
        validate_portable_paths(
            [
                ".github/workflows/quality.yml",
                "README.md",
                "app/src/main/MainActivity.kt",
                "gateway/src/server.mjs",
            ]
        )

    def test_rejects_casefold_collisions(self):
        with self.assertRaisesRegex(ValueError, "portable repository path collision"):
            validate_portable_paths(["Docs/README.md", "docs/readme.md"])

    def test_rejects_non_nfc_paths(self):
        decomposed = "docs/cafe\u0301.md"
        with self.assertRaisesRegex(ValueError, "NFC-normalized"):
            validate_portable_paths([decomposed])

    def test_rejects_windows_reserved_basenames(self):
        for path in (
            "CON",
            "docs/aux.txt",
            "nested/NUL.json",
            "tools/Com1.py",
            "artifacts/lPt9.log",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "Windows-reserved basename"):
                    validate_portable_paths([path])

    def test_rejects_windows_superscript_device_basenames(self):
        for path in (
            "COM¹",
            "docs/com².txt",
            "nested/Com³.json",
            "LPT¹",
            "tools/lpt².py",
            "artifacts/LpT³.log",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "Windows-reserved basename"):
                    validate_portable_paths([path])

    def test_rejects_windows_forbidden_filename_characters(self):
        for char in '<>:"\\|?*':
            with self.subTest(char=repr(char)):
                path = f"docs/bad{char}name.md"
                with self.assertRaisesRegex(
                    ValueError,
                    "Windows-reserved filename characters",
                ):
                    validate_portable_paths([path])

    def test_rejects_trailing_space_or_period(self):
        for path in ("docs/name. ", "docs/name.", "docs/name "):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "space or period"):
                    validate_portable_paths([path])

    def test_rejects_ascii_control_characters(self):
        for codepoint in (1, 7, 27, 31):
            with self.subTest(codepoint=codepoint):
                path = f"docs/bad{chr(codepoint)}name.md"
                with self.assertRaisesRegex(ValueError, "ASCII control"):
                    validate_portable_paths([path])

    def test_rejects_invisible_unicode_path_controls(self):
        for codepoint in (0x0085, 0x00AD, 0x200B, 0x200D, 0x202E, 0x2060):
            with self.subTest(codepoint=f"U+{codepoint:04X}"):
                path = f"docs/bad{chr(codepoint)}name.md"
                with self.assertRaisesRegex(
                    ValueError,
                    "Unicode control and format characters",
                ):
                    validate_portable_paths([path])

    def test_rejects_unicode_line_and_paragraph_separators(self):
        for codepoint in (0x2028, 0x2029):
            with self.subTest(codepoint=f"U+{codepoint:04X}"):
                path = f"docs/bad{chr(codepoint)}name.md"
                with self.assertRaisesRegex(
                    ValueError,
                    "Unicode line and paragraph separators",
                ):
                    validate_portable_paths([path])

    def test_rejects_duplicate_or_empty_path_sets(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            validate_portable_paths([])
        with self.assertRaisesRegex(ValueError, "portable repository path collision"):
            validate_portable_paths(["README.md", "README.md"])


if __name__ == "__main__":
    unittest.main()
