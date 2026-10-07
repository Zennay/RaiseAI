#!/usr/bin/env python3
"""Inspect exported Raise AI sensor traces for orientation separation.

This is an exploratory calibration helper, not the canonical V1 acceptance
analyzer. Input still needs to be unambiguous: malformed or non-finite sensor
data must fail closed instead of producing a plausible-looking threshold.
"""

from __future__ import annotations

import argparse
import csv
import errno
import math
import os
import stat
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ALLOWED_LABELS = {"mouth_raise", "view_time", "normal_move"}
REQUIRED_COLUMNS = {"label", "session_id", "elapsed_ms", "x", "y", "z"}


class TraceError(ValueError):
    pass


@dataclass(frozen=True)
class Sample:
    elapsed_ms: int
    x: float
    y: float
    z: float


def _parse_positive_int(row: dict[str, str | None], key: str, line: int) -> int:
    try:
        value = int(row[key] or "")
    except (KeyError, TypeError, ValueError) as exc:
        raise TraceError(f"line {line}: {key} must be an integer") from exc
    if value <= 0:
        raise TraceError(f"line {line}: {key} must be positive")
    return value


def _parse_non_negative_int(row: dict[str, str | None], key: str, line: int) -> int:
    try:
        value = int(row[key] or "")
    except (KeyError, TypeError, ValueError) as exc:
        raise TraceError(f"line {line}: {key} must be an integer") from exc
    if value < 0:
        raise TraceError(f"line {line}: {key} must be non-negative")
    return value


def _parse_finite_float(row: dict[str, str | None], key: str, line: int) -> float:
    try:
        value = float(row[key] or "")
    except (KeyError, TypeError, ValueError) as exc:
        raise TraceError(f"line {line}: {key} must be numeric") from exc
    if not math.isfinite(value):
        raise TraceError(f"line {line}: {key} must be finite")
    return value


def read_sessions(path: Path) -> dict[tuple[str, int], list[Sample]]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise TraceError("platform does not support safe no-follow trace reads")

    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise TraceError("trace CSV must not be a symlink") from exc
        raise TraceError(str(exc)) from exc

    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise TraceError(f"trace CSV is not a regular file: {path}")

        sessions: dict[tuple[str, int], list[Sample]] = defaultdict(list)
        labels_by_session: dict[int, str] = {}
        last_elapsed_by_session: dict[int, int] = {}

        try:
            with os.fdopen(
                fd,
                "r",
                encoding="utf-8",
                newline="",
                closefd=False,
            ) as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise TraceError("trace CSV has no header")

                duplicates = sorted(
                    name
                    for name, count in Counter(reader.fieldnames).items()
                    if count > 1
                )
                if duplicates:
                    raise TraceError(
                        f"duplicate columns: {', '.join(duplicates)}"
                    )

                actual_columns = set(reader.fieldnames)
                missing = REQUIRED_COLUMNS - actual_columns
                unexpected = actual_columns - REQUIRED_COLUMNS
                if missing:
                    raise TraceError(
                        f"missing columns: {', '.join(sorted(missing))}"
                    )
                if unexpected:
                    raise TraceError(
                        f"unexpected columns: {', '.join(sorted(unexpected))}"
                    )

                for line, row in enumerate(reader, start=2):
                    if None in row:
                        raise TraceError(
                            f"line {line}: unexpected extra CSV fields"
                        )
                    if any(value is None for value in row.values()):
                        raise TraceError(f"line {line}: missing CSV field")

                    label = (row.get("label") or "").strip()
                    if label not in ALLOWED_LABELS:
                        raise TraceError(
                            f"line {line}: unknown label {label!r}"
                        )

                    session_id = _parse_positive_int(
                        row, "session_id", line
                    )
                    elapsed_ms = _parse_non_negative_int(
                        row, "elapsed_ms", line
                    )

                    previous_label = labels_by_session.setdefault(
                        session_id, label
                    )
                    if previous_label != label:
                        raise TraceError(
                            f"session {session_id} mixes labels "
                            f"{previous_label!r} and {label!r}"
                        )

                    previous_elapsed = last_elapsed_by_session.get(
                        session_id
                    )
                    if (
                        previous_elapsed is not None
                        and elapsed_ms < previous_elapsed
                    ):
                        raise TraceError(
                            f"line {line}: elapsed_ms moved backwards "
                            f"in session {session_id}"
                        )
                    last_elapsed_by_session[session_id] = elapsed_ms

                    sessions[(label, session_id)].append(
                        Sample(
                            elapsed_ms=elapsed_ms,
                            x=_parse_finite_float(row, "x", line),
                            y=_parse_finite_float(row, "y", line),
                            z=_parse_finite_float(row, "z", line),
                        )
                    )
        except UnicodeDecodeError as exc:
            raise TraceError("trace CSV must be valid UTF-8") from exc
        except csv.Error as exc:
            raise TraceError(f"invalid CSV: {exc}") from exc

        if not sessions:
            raise TraceError("trace CSV contains no samples")
        return dict(sessions)
    finally:
        os.close(fd)


def normalize(vector: tuple[float, float, float]) -> tuple[float, float, float] | None:
    if not all(math.isfinite(component) for component in vector):
        return None
    length = math.sqrt(sum(component * component for component in vector))
    if not math.isfinite(length) or length < 1e-9:
        return None
    return tuple(component / length for component in vector)


def avg_orientation(samples: list[Sample], tail_ms: int = 800) -> tuple[float, float, float] | None:
    if not samples:
        return None
    end = max(sample.elapsed_ms for sample in samples)
    tail = [sample for sample in samples if sample.elapsed_ms >= end - tail_ms] or samples
    return normalize(
        (
            statistics.fmean(sample.x for sample in tail),
            statistics.fmean(sample.y for sample in tail),
            statistics.fmean(sample.z for sample in tail),
        )
    )


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    value = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, value))


def render_analysis(sessions: dict[tuple[str, int], list[Sample]]) -> str:
    mouth = [
        orientation
        for (label, _), samples in sessions.items()
        if label == "mouth_raise"
        for orientation in [avg_orientation(samples)]
        if orientation is not None
    ]
    if not mouth:
        raise TraceError("no usable mouth_raise sessions found")

    reference = normalize(
        tuple(statistics.fmean(orientation[index] for orientation in mouth) for index in range(3))
    )
    if reference is None:
        raise TraceError("mouth_raise orientations cancel to a degenerate reference")

    counts = Counter(label for label, _ in sessions)
    by_label: dict[str, list[float]] = defaultdict(list)
    for (label, _), samples in sessions.items():
        orientation = avg_orientation(samples)
        if orientation is not None:
            by_label[label].append(dot(reference, orientation))

    lines = ["Sessions:"]
    for label in sorted(counts):
        lines.append(f"  {label}: {counts[label]}")

    lines.extend(
        [
            "",
            "Reference mouth orientation:",
            "  x={:.4f} y={:.4f} z={:.4f}".format(*reference),
            "",
            "End-pose similarity to mouth reference (1.0 = identical):",
        ]
    )
    for label in sorted(by_label):
        values = by_label[label]
        lines.append(
            f"  {label:12s} min={min(values):.4f} "
            f"avg={statistics.fmean(values):.4f} max={max(values):.4f}"
        )

    mouth_values = by_label.get("mouth_raise", [])
    negative_values = by_label.get("view_time", []) + by_label.get("normal_move", [])
    if mouth_values and negative_values:
        low_mouth = min(mouth_values)
        high_negative = max(negative_values)
        if low_mouth > high_negative:
            suggested = max(0.90, min(0.995, (low_mouth + high_negative) / 2))
            lines.extend(
                [
                    "",
                    "Good orientation separation detected.",
                    f"  Suggested similarityThreshold ≈ {suggested:.4f}",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "Orientation alone overlaps between mouth and non-mouth samples.",
                    "  Keep the movement/hold state machine and collect more samples before tuning.",
                    f"  mouth minimum={low_mouth:.4f}, non-mouth maximum={high_negative:.4f}",
                ]
            )
    else:
        lines.extend(
            [
                "",
                "Need mouth_raise plus view_time/normal_move sessions before suggesting a threshold.",
            ]
        )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_csv", nargs="?", type=Path, default=Path("sensor-traces.csv"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        sessions = read_sessions(args.trace_csv)
        output = render_analysis(sessions)
    except TraceError as exc:
        print(f"Invalid trace CSV: {exc}", file=sys.stderr)
        return 2

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
