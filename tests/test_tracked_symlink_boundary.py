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
                link = ROOT / filename
                self.assertTrue(link.is_symlink(), f"{filename}: Git symlink missing from checkout")
                validate_target(filename, link.readlink().as_posix())

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
