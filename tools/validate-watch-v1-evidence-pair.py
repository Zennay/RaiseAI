#!/usr/bin/env python3
"""Validate that Raise AI V1 trace and trial evidence describe the same captures."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


class PairError(ValueError):
    pass


def _load_tool(name: str, filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PairError(f"unable to load evidence tool: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_pair(trace_path: Path, trial_path: Path) -> dict[str, Any]:
    trace = _load_tool("raise_watch_trace_analyzer_pair", "analyze-watch-sensor-traces.py")
    trial = _load_tool("raise_watch_trial_analyzer_pair", "analyze-watch-sensor-trials.py")

    try:
        samples = trace.read_samples(trace_path)
        trials = trial.read_trials(trial_path)
    except (trace.TraceError, trial.TrialError) as exc:
        raise PairError(str(exc)) from exc

    trace_rows: dict[int, list[Any]] = {}
    for sample in samples:
        trace_rows.setdefault(sample.session_id, []).append(sample)

    trial_by_session = {row["session_id"]: row for row in trials}
    trace_ids = set(trace_rows)
    trial_ids = set(trial_by_session)

    missing_trials = sorted(trace_ids - trial_ids)
    missing_traces = sorted(trial_ids - trace_ids)
    if missing_trials:
        raise PairError(
            "trace sessions are missing trial outcomes: "
            + ", ".join(str(value) for value in missing_trials)
        )
    if missing_traces:
        raise PairError(
            "trial outcomes are missing raw trace sessions: "
            + ", ".join(str(value) for value in missing_traces)
        )

    label_counts: dict[str, int] = {}
    for session_id in sorted(trace_ids):
        rows = trace_rows[session_id]
        trial_row = trial_by_session[session_id]
        trace_label = rows[0].label
        if trial_row["label"] != trace_label:
            raise PairError(
                f"session {session_id}: trace label {trace_label!r} "
                f"does not match trial label {trial_row['label']!r}"
            )
        if trial_row["sample_count"] != len(rows):
            raise PairError(
                f"session {session_id}: trace sample count {len(rows)} "
                f"does not match trial sample_count {trial_row['sample_count']}"
            )
        max_elapsed_ms = max(row.elapsed_ms for row in rows)
        if trial_row["duration_ms"] < max_elapsed_ms:
            raise PairError(
                f"session {session_id}: trial duration {trial_row['duration_ms']}ms "
                f"is shorter than latest trace sample {max_elapsed_ms}ms"
            )
        label_counts[trace_label] = label_counts.get(trace_label, 0) + 1

    return {
        "schema_version": 1,
        "valid": True,
        "paired_session_count": len(trace_ids),
        "labels": {key: label_counts[key] for key in sorted(label_counts)},
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_csv", type=Path)
    parser.add_argument("trial_csv", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = validate_pair(args.trace_csv, args.trial_csv)
    except PairError as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, separators=(",", ":")))
        return 2

    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
