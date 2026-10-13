"""Fail closed on unsafe tracked Git symlink targets.

Run: python3 -m unittest discover -s tests -p 'test_tracked_symlink_boundary.py'
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def validate_target(path: str, target: str) -> None:
    """Only relative, repository-contained symlink targets are allowed."""
    if not path or path.startswith("/") or chr(0) in path or any(part == ".." for part in pathlib.PurePosixPath(path).parts):
        raise ValueError("invalid tracked symlink path")
    if not target or chr(0) in target or pathlib.PurePosixPath(target).is_absolute():
        raise ValueError(f"{path}: absolute or empty symlink target")
    parts = []
    for component in (pathlib.PurePosixPath(path).parent / target).parts:
        if component in ("", "."):
            continue
        if component == "..":
            if not parts:
                raise ValueError(f"{path}: symlink target escapes repository")
            parts.pop()
        else:
            parts.append(component)



def validate_checkout_symlink(root: pathlib.Path, name: str) -> None:
    """Validate the lexical target and the fully resolved symlink chain."""
    link = root / name
    if not link.is_symlink():
        raise ValueError(f"{name}: checked-out link is missing")
    validate_target(name, link.readlink().as_posix())
    repo_root = root.resolve(strict=True)
    try:
        destination = link.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{name}: invalid or unresolved symlink chain") from exc
    if not destination.is_relative_to(repo_root):
        raise ValueError(f"{name}: symlink chain escapes repository")


def tracked_symlinks():
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
    for entry in filter(None, raw.split(b"\0")):
        metadata, separator, filename = entry.partition(b"\t")
        if not separator:
            raise ValueError("invalid git index entry")
        parts = metadata.split()
        if len(parts) != 3:
            raise ValueError("invalid git index metadata")
        mode, _, stage = parts
        if stage != b"0":
            raise ValueError("unmerged git index entry")
        if mode == b"120000":
            yield filename.decode("utf-8", "strict")


class TrackedSymlinkBoundaryTests(unittest.TestCase):
    def test_tracked_symlink_targets_stay_inside_repository(self):
        for filename in tracked_symlinks():
            with self.subTest(path=filename):
                validate_checkout_symlink(ROOT, filename)

    def test_symlink_chain_that_escapes_repository_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            parent = pathlib.Path(folder)
            repo = parent / "repo"
            repo.mkdir()
            outside = parent / "private.txt"
            outside.write_text("private", encoding="utf-8")
            (repo / "indirect").symlink_to("../private.txt")
            (repo / "public-link").symlink_to("indirect")
            with self.assertRaisesRegex(ValueError, "chain escapes repository"):
                validate_checkout_symlink(repo, "public-link")

    def test_internal_symlink_chain_is_allowed_and_broken_chain_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            repo = pathlib.Path(folder) / "repo"
            repo.mkdir()
            (repo / "file.txt").write_text("ok", encoding="utf-8")
            (repo / "indirect").symlink_to("file.txt")
            (repo / "public-link").symlink_to("indirect")
            validate_checkout_symlink(repo, "public-link")
            (repo / "indirect").unlink()
            with self.assertRaisesRegex(ValueError, "invalid or unresolved"):
                validate_checkout_symlink(repo, "public-link")

    def test_rejects_absolute_and_parent_escape(self):
        for path, target in (
            ("tool-link", "/etc/passwd"),
            ("scripts/tool", "../../outside"),
            ("scripts/tool", ""),
            ("scripts/tool", "../.."),
            ("scripts/tool", "bad" + chr(0) + "target"),
            ("../unsafe", "tool"),
        ):
            with self.subTest(path=path, target=target):
                with self.assertRaises(ValueError):
                    validate_target(path, target)


    def test_index_parser_rejects_unmerged_entries(self):
        from unittest import mock
        sample = b"120000 deadbeef 1" + bytes([9]) + b"test-link" + bytes([0])
        with mock.patch.object(subprocess, "check_output", return_value=sample):
            with self.assertRaisesRegex(ValueError, "unmerged git index entry"):
                list(tracked_symlinks())

    def test_index_parser_detects_symlinks_only(self):
        from unittest import mock
        sample = b"100644 deadbeef 0" + bytes([9]) + b"README.md" + bytes([0])
        sample += b"120000 facebeef 0" + bytes([9]) + b"safe-link" + bytes([0])
        with mock.patch.object(subprocess, "check_output", return_value=sample):
            self.assertEqual(list(tracked_symlinks()), ["safe-link"])

    def test_index_parser_rejects_malformed_metadata(self):
        from unittest import mock
        for entry in (b"broken-entry" + bytes([0]), b"120000 facebeef" + bytes([9]) + b"link" + bytes([0])):
            with self.subTest(entry=entry):
                with mock.patch.object(subprocess, "check_output", return_value=entry):
                    with self.assertRaisesRegex(ValueError, "invalid git index"):
                        list(tracked_symlinks())

    def test_accepts_repository_local_relative_links(self):
        for path, target in (
            ("scripts/tool", "../tools/utility.sh"),
            ("tool", "scripts/run.sh"),
            ("a/b/tool", "../run.sh"),
        ):
            with self.subTest(path=path, target=target):
                validate_target(path, target)


if __name__ == "__main__":
    unittest.main()
