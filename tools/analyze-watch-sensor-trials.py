#!/usr/bin/env python3
"""Evaluate Raise AI Watch gesture reliability trials against the V1 gate."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ALLOWED_LABELS = {"mouth_raise", "view_time", "normal_move"}
NON_TRIGGER_LABELS = {"view_time", "normal_move"}
REQUIRED_COLUMNS = {
    "label",
    "session_id",
    "duration_ms",
    "sample_count",
    "detector_triggered",
    "max_similarity",
    "app_version",
    "source_revision",
    "detector_config",
}


class TrialError(ValueError):
    pass


def _parse_bool(value: str, *, line: int) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise TrialError(f"line {line}: detector_triggered must be true or false")


def read_trials(path: Path) -> list[dict[str, Any]]:
    try:
        handle = path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise TrialError(str(exc)) from exc

    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise TrialError("trial CSV has no header")
        columns = set(reader.fieldnames)
        missing = REQUIRED_COLUMNS - columns
        unexpected = columns - REQUIRED_COLUMNS
        if missing:
            raise TrialError(f"missing columns: {', '.join(sorted(missing))}")
        if unexpected:
            raise TrialError(f"unexpected columns: {', '.join(sorted(unexpected))}")

        rows: list[dict[str, Any]] = []
        seen_sessions: set[int] = set()
        for line, row in enumerate(reader, start=2):
            label = (row.get("label") or "").strip()
            if label not in ALLOWED_LABELS:
                raise TrialError(f"line {line}: unknown label {label!r}")
            try:
                session_id = int(row["session_id"])
                duration_ms = int(row["duration_ms"])
                sample_count = int(row["sample_count"])
                max_similarity = float(row["max_similarity"])
            except (KeyError, TypeError, ValueError) as exc:
                raise TrialError(f"line {line}: invalid numeric field") from exc

            if session_id <= 0:
                raise TrialError(f"line {line}: session_id must be positive")
            if session_id in seen_sessions:
                raise TrialError(f"line {line}: duplicate session_id {session_id}")
            seen_sessions.add(session_id)
            if duration_ms < 0 or sample_count < 0:
                raise TrialError(f"line {line}: duration/sample count must be non-negative")
            if not -1.0 <= max_similarity <= 1.0:
                raise TrialError(f"line {line}: max_similarity must be between -1 and 1")

            app_version = (row.get("app_version") or "").strip()
            source_revision = (row.get("source_revision") or "").strip().lower()
            detector_config = (row.get("detector_config") or "").strip()
            if not app_version:
                raise TrialError(f"line {line}: app_version must be non-empty")
            if len(source_revision) != 40 or any(char not in "0123456789abcdef" for char in source_revision):
                raise TrialError(f"line {line}: source_revision must be a 40-character Git SHA")
            if not detector_config or detector_config == "missing" or "," in detector_config:
                raise TrialError(f"line {line}: detector_config must be a concrete comma-free id")

            rows.append(
                {
                    "label": label,
                    "session_id": session_id,
                    "duration_ms": duration_ms,
                    "sample_count": sample_count,
                    "detector_triggered": _parse_bool(row["detector_triggered"], line=line),
                    "max_similarity": max_similarity,
                    "app_version": app_version,
                    "source_revision": source_revision,
                    "detector_config": detector_config,
                }
            )

    if not rows:
        raise TrialError("trial CSV contains no trials")
    return rows


def build_report(
    trials: list[dict[str, Any]],
    *,
    min_duration_ms: int = 3_000,
    min_samples: int = 20,
    required_raises: int = 30,
    required_non_triggers: int = 100,
    min_detection_rate: float = 0.90,
    max_false_trigger_rate: float = 0.05,
    expect_app_version: str | None = None,
    expect_source_revision: str | None = None,
) -> dict[str, Any]:
    if min_duration_ms < 0 or min_samples <= 0:
        raise TrialError("invalid trial quality thresholds")
    if required_raises < 0 or required_non_triggers < 0:
        raise TrialError("required trial counts must be non-negative")
    if not 0 <= min_detection_rate <= 1 or not 0 <= max_false_trigger_rate <= 1:
        raise TrialError("rate thresholds must be between 0 and 1")

    qualifying = [
        trial
        for trial in trials
        if trial["duration_ms"] >= min_duration_ms and trial["sample_count"] >= min_samples
    ]
    raises = [trial for trial in qualifying if trial["label"] == "mouth_raise"]
    non_triggers = [trial for trial in qualifying if trial["label"] in NON_TRIGGER_LABELS]

    # Evidence identity is a file-level invariant, not a scoring-quality filter.
    # A short/incomplete trial from another build must fail closed instead of being
    # silently excluded before provenance validation.
    app_versions = sorted({trial["app_version"] for trial in trials})
    source_revisions = sorted({trial["source_revision"] for trial in trials})
    detector_configs = sorted({trial["detector_config"] for trial in trials})
    if len(app_versions) > 1:
        raise TrialError(f"trials mix app versions: {', '.join(app_versions)}")
    if len(source_revisions) > 1:
        raise TrialError("trials mix source revisions")
    if len(detector_configs) > 1:
        raise TrialError("trials mix detector configurations")

    if expect_app_version is not None and app_versions[0] != expect_app_version:
        raise TrialError(
            f"trial app_version {app_versions[0]!r} does not match expected {expect_app_version!r}"
        )
    if expect_source_revision is not None:
        expected_revision = expect_source_revision.strip().lower()
        if len(expected_revision) != 40 or any(char not in "0123456789abcdef" for char in expected_revision):
            raise TrialError("expected source revision must be a 40-character Git SHA")
        if source_revisions[0] != expected_revision:
            raise TrialError(
                f"trial source_revision {source_revisions[0]!r} does not match expected {expected_revision!r}"
            )

    detected_raises = sum(1 for trial in raises if trial["detector_triggered"])
    false_triggers = sum(1 for trial in non_triggers if trial["detector_triggered"])
    detection_rate = detected_raises / len(raises) if raises else 0.0
    false_trigger_rate = false_triggers / len(non_triggers) if non_triggers else 0.0

    count_gate = len(raises) >= required_raises and len(non_triggers) >= required_non_triggers
    rate_gate = detection_rate >= min_detection_rate and false_trigger_rate <= max_false_trigger_rate
    ready = count_gate and rate_gate

    return {
        "schema_version": 1,
        "v1_gate_passed": ready,
        "evidence_identity": {
            "app_version": app_versions[0] if app_versions else None,
            "source_revision": source_revisions[0] if source_revisions else None,
            "detector_config": detector_configs[0] if detector_configs else None,
        },
        "requirements": {
            "mouth_raise_trials": required_raises,
            "non_trigger_trials": required_non_triggers,
            "min_detection_rate": min_detection_rate,
            "max_false_trigger_rate": max_false_trigger_rate,
        },
        "results": {
            "mouth_raise_trials": len(raises),
            "mouth_raise_detected": detected_raises,
            "detection_rate": round(detection_rate, 6),
            "non_trigger_trials": len(non_triggers),
            "false_triggers": false_triggers,
            "false_trigger_rate": round(false_trigger_rate, 6),
        },
        "remaining": {
            "mouth_raise_trials": max(0, required_raises - len(raises)),
            "non_trigger_trials": max(0, required_non_triggers - len(non_triggers)),
        },
        "rejected_trial_count": len(trials) - len(qualifying),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial_csv", type=Path)
    parser.add_argument("--min-duration-ms", type=int, default=3_000)
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--required-raises", type=int, default=30)
    parser.add_argument("--required-non-triggers", type=int, default=100)
    parser.add_argument("--min-detection-rate", type=float, default=0.90)
    parser.add_argument("--max-false-trigger-rate", type=float, default=0.05)
    parser.add_argument("--expect-app-version")
    parser.add_argument("--expect-source-revision")
    parser.add_argument("--require-v1-gate", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        trials = read_trials(args.trial_csv)
        report = build_report(
            trials,
            min_duration_ms=args.min_duration_ms,
            min_samples=args.min_samples,
            required_raises=args.required_raises,
            required_non_triggers=args.required_non_triggers,
            min_detection_rate=args.min_detection_rate,
            max_false_trigger_rate=args.max_false_trigger_rate,
            expect_app_version=args.expect_app_version,
            expect_source_revision=args.expect_source_revision,
        )
    except TrialError as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, separators=(",", ":")))
        return 2

    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    if args.require_v1_gate and not report["v1_gate_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
