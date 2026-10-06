#!/usr/bin/env python3
"""Summarize Raise AI Watch sensor traces and evaluate V1 dataset readiness.

The V1 roadmap evidence gate requires at least 30 intentional mouth raises and
100 representative non-trigger movements. This tool validates the exported CSV
shape, groups samples into capture sessions, rejects malformed sessions, and
reports how much qualifying evidence has actually been collected.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ALLOWED_LABELS = {"mouth_raise", "view_time", "normal_move"}
NON_TRIGGER_LABELS = {"view_time", "normal_move"}
REQUIRED_COLUMNS = {"label", "session_id", "elapsed_ms", "x", "y", "z"}


class TraceError(ValueError):
    pass


@dataclass(frozen=True)
class Sample:
    label: str
    session_id: int
    elapsed_ms: int
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class SessionSummary:
    session_id: int
    label: str
    sample_count: int
    duration_ms: int
    monotonic: bool
    qualifying: bool


def _parse_int(row: dict[str, str], key: str, line: int) -> int:
    try:
        return int(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise TraceError(f"line {line}: {key} must be an integer") from exc


def _parse_float(row: dict[str, str], key: str, line: int) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise TraceError(f"line {line}: {key} must be numeric") from exc
    if not math.isfinite(value):
        raise TraceError(f"line {line}: {key} must be a finite number")
    return value


def read_samples(path: Path) -> list[Sample]:
    try:
        handle = path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise TraceError(str(exc)) from exc

    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise TraceError("trace CSV has no header")
        duplicate_columns = sorted(
            name for name, count in Counter(reader.fieldnames).items() if count > 1
        )
        if duplicate_columns:
            raise TraceError(f"duplicate columns: {', '.join(duplicate_columns)}")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        unexpected = set(reader.fieldnames) - REQUIRED_COLUMNS
        if missing:
            raise TraceError(f"missing columns: {', '.join(sorted(missing))}")
        if unexpected:
            raise TraceError(f"unexpected columns: {', '.join(sorted(unexpected))}")

        samples: list[Sample] = []
        labels_by_session: dict[int, str] = {}
        for line, row in enumerate(reader, start=2):
            if None in row:
                raise TraceError(f"line {line}: unexpected extra CSV fields")
            label = (row.get("label") or "").strip()
            if label not in ALLOWED_LABELS:
                raise TraceError(f"line {line}: unknown label {label!r}")
            session_id = _parse_int(row, "session_id", line)
            elapsed_ms = _parse_int(row, "elapsed_ms", line)
            if session_id <= 0:
                raise TraceError(f"line {line}: session_id must be positive")
            if elapsed_ms < 0:
                raise TraceError(f"line {line}: elapsed_ms must be non-negative")

            previous_label = labels_by_session.setdefault(session_id, label)
            if previous_label != label:
                raise TraceError(
                    f"session {session_id} mixes labels {previous_label!r} and {label!r}"
                )

            samples.append(
                Sample(
                    label=label,
                    session_id=session_id,
                    elapsed_ms=elapsed_ms,
                    x=_parse_float(row, "x", line),
                    y=_parse_float(row, "y", line),
                    z=_parse_float(row, "z", line),
                )
            )

    if not samples:
        raise TraceError("trace CSV contains no samples")
    return samples


def summarize_sessions(
    samples: Iterable[Sample],
    *,
    min_duration_ms: int = 3_000,
    min_samples: int = 20,
) -> list[SessionSummary]:
    if min_duration_ms < 0:
        raise TraceError("min_duration_ms must be non-negative")
    if min_samples <= 0:
        raise TraceError("min_samples must be positive")

    grouped: dict[int, list[Sample]] = {}
    for sample in samples:
        grouped.setdefault(sample.session_id, []).append(sample)

    summaries: list[SessionSummary] = []
    for session_id, rows in sorted(grouped.items()):
        label = rows[0].label
        elapsed = [row.elapsed_ms for row in rows]
        monotonic = all(current >= previous for previous, current in zip(elapsed, elapsed[1:]))
        duration_ms = max(elapsed) - min(elapsed) if elapsed else 0
        qualifying = monotonic and len(rows) >= min_samples and duration_ms >= min_duration_ms
        summaries.append(
            SessionSummary(
                session_id=session_id,
                label=label,
                sample_count=len(rows),
                duration_ms=duration_ms,
                monotonic=monotonic,
                qualifying=qualifying,
            )
        )
    return summaries


def build_report(
    sessions: list[SessionSummary],
    *,
    required_raises: int = 30,
    required_non_triggers: int = 100,
) -> dict[str, object]:
    if required_raises < 0 or required_non_triggers < 0:
        raise TraceError("required session counts must be non-negative")

    all_counts = Counter(session.label for session in sessions)
    qualified = [session for session in sessions if session.qualifying]
    qualified_counts = Counter(session.label for session in qualified)

    mouth_raises = qualified_counts["mouth_raise"]
    non_triggers = sum(qualified_counts[label] for label in NON_TRIGGER_LABELS)
    ready = mouth_raises >= required_raises and non_triggers >= required_non_triggers

    return {
        "schema_version": 1,
        "ready_for_v1_reliability_test": ready,
        "requirements": {
            "mouth_raise_sessions": required_raises,
            "non_trigger_sessions": required_non_triggers,
        },
        "qualified": {
            "mouth_raise": mouth_raises,
            "view_time": qualified_counts["view_time"],
            "normal_move": qualified_counts["normal_move"],
            "non_trigger_total": non_triggers,
            "total": len(qualified),
        },
        "remaining": {
            "mouth_raise": max(0, required_raises - mouth_raises),
            "non_trigger_total": max(0, required_non_triggers - non_triggers),
        },
        "captured": {
            "mouth_raise": all_counts["mouth_raise"],
            "view_time": all_counts["view_time"],
            "normal_move": all_counts["normal_move"],
            "total": len(sessions),
        },
        "rejected_sessions": [
            {
                "session_id": session.session_id,
                "label": session.label,
                "sample_count": session.sample_count,
                "duration_ms": session.duration_ms,
                "monotonic": session.monotonic,
            }
            for session in sessions
            if not session.qualifying
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_csv", type=Path)
    parser.add_argument("--min-duration-ms", type=int, default=3_000)
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--required-raises", type=int, default=30)
    parser.add_argument("--required-non-triggers", type=int, default=100)
    parser.add_argument(
        "--require-v1-gate",
        action="store_true",
        help="exit non-zero until the V1 30/100 dataset gate is satisfied",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        samples = read_samples(args.trace_csv)
        sessions = summarize_sessions(
            samples,
            min_duration_ms=args.min_duration_ms,
            min_samples=args.min_samples,
        )
        report = build_report(
            sessions,
            required_raises=args.required_raises,
            required_non_triggers=args.required_non_triggers,
        )
    except TraceError as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, separators=(",", ":")))
        return 2

    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    if args.require_v1_gate and not report["ready_for_v1_reliability_test"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
