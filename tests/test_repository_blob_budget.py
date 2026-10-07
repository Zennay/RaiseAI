import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "repository-blob-budget.yml"
MAX_TRACKED_BLOB_BYTES = 5 * 1024 * 1024


def tracked_blob_entries(*, root: pathlib.Path = ROOT) -> list[tuple[str, int]]:
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root)
    indexed: list[tuple[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("tracked index entry must have canonical Git metadata") from exc

        if stage != "0":
            raise ValueError(f"{path!r}: unmerged Git index stage {stage} is forbidden")
        if mode not in {"100644", "100755"}:
            raise ValueError(f"{path!r}: tracked entry mode {mode} is not a regular file")
        indexed.append((path, object_id))

    if not indexed:
        raise ValueError("tracked blob discovery must not be empty")

    request = "".join(f"{object_id}\n" for _path, object_id in indexed).encode("ascii")
    completed = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        cwd=root,
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    rows = completed.stdout.decode("ascii", errors="strict").splitlines()
    if len(rows) != len(indexed):
        raise ValueError("Git object metadata count does not match tracked index")

    entries: list[tuple[str, int]] = []
    for (path, expected_id), row in zip(indexed, rows, strict=True):
        try:
            object_id, object_type, raw_size = row.split()
            size = int(raw_size)
        except ValueError as exc:
            raise ValueError(f"{path!r}: invalid Git object metadata") from exc
        if object_id != expected_id:
            raise ValueError(f"{path!r}: Git object lookup returned an unexpected object")
        if object_type != "blob":
            raise ValueError(f"{path!r}: tracked regular file must resolve to a blob")
        if size < 0:
            raise ValueError(f"{path!r}: Git blob size must not be negative")
        entries.append((path, size))

    return entries


def validate_blob_budget(
    entries: list[tuple[str, int]],
    *,
    max_blob_bytes: int = MAX_TRACKED_BLOB_BYTES,
) -> None:
    if max_blob_bytes <= 0:
        raise ValueError("tracked blob budget must be positive")
    if not entries:
        raise ValueError("tracked blob discovery must not be empty")

    for path, size in entries:
        if not path:
            raise ValueError("tracked blob path must not be empty")
        if size < 0:
            raise ValueError(f"{path!r}: tracked blob size must not be negative")
        if size > max_blob_bytes:
            raise ValueError(
                f"{path!r}: tracked blob is {size} bytes; "
                f"limit is {max_blob_bytes} bytes"
            )


class RepositoryBlobBudgetTests(unittest.TestCase):
    def test_every_tracked_blob_stays_within_repository_budget(self):
        entries = tracked_blob_entries()
        self.assertTrue(entries)
        validate_blob_budget(entries)

    def test_accepts_empty_and_boundary_sized_files(self):
        validate_blob_budget(
            [
                ("empty.txt", 0),
                ("boundary.bin", MAX_TRACKED_BLOB_BYTES),
            ]
        )

    def test_rejects_oversized_blob(self):
        with self.assertRaisesRegex(ValueError, "tracked blob is"):
            validate_blob_budget(
                [("too-large.bin", MAX_TRACKED_BLOB_BYTES + 1)]
            )

    def test_rejects_invalid_budget(self):
        for budget in (0, -1):
            with self.subTest(budget=budget):
                with self.assertRaisesRegex(ValueError, "budget must be positive"):
                    validate_blob_budget([("file.txt", 1)], max_blob_bytes=budget)

    def test_rejects_empty_discovery(self):
        with self.assertRaisesRegex(ValueError, "discovery must not be empty"):
            validate_blob_budget([])

    def test_rejects_invalid_entry_metadata(self):
        with self.assertRaisesRegex(ValueError, "path must not be empty"):
            validate_blob_budget([("", 1)])
        with self.assertRaisesRegex(ValueError, "size must not be negative"):
            validate_blob_budget([("bad.bin", -1)])

    def test_workflow_is_read_only_exact_head_and_vps_bound(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotRegex(text, r"(?m)^\s+[A-Za-z0-9_-]+:\s*write\s*$")
        self.assertNotRegex(text, r"\$\{\{\s*secrets\.")
        self.assertIn(
            "    runs-on: [self-hosted, linux, x64, vps-bb300bba]",
            text,
        )
        self.assertNotIn("ubuntu-latest", text)
        self.assertNotIn("ubuntu-24.04", text)
        self.assertIn("    timeout-minutes: 10", text)
        self.assertIn('          test "$(hostname)" = "vps-bb300bba"', text)
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            text,
        )
        self.assertIn("          persist-credentials: false", text)
        self.assertIn(
            "ref: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}",
            text,
        )
        self.assertIn(
            "EXPECTED_SHA: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}",
            text,
        )

    def test_workflow_runs_for_main_pushes_and_all_pull_requests(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  push:\n    branches:\n      - main", text)
        self.assertIn("  pull_request:\n", text)
        self.assertNotIn("    paths:", text)
        self.assertNotIn("    paths-ignore:", text)
        self.assertIn("  cancel-in-progress: true", text)


if __name__ == "__main__":
    unittest.main()
