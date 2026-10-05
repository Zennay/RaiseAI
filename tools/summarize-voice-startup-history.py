#!/usr/bin/env python3
import argparse
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path


MAX_HISTORY_SAMPLES = 50


def fail(message: str) -> "NoReturn":
    raise ValueError(message)


def parse_utc(value: object, line_number: int) -> datetime:
    if not isinstance(value, str) or not value:
        fail(f"line {line_number}: recorded_at_utc must be a non-empty string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        fail(f"line {line_number}: invalid recorded_at_utc: {exc}")
    if parsed.tzinfo is None:
        fail(f"line {line_number}: recorded_at_utc must include timezone")
    return parsed


def load_history(path: Path) -> list[dict]:
    if not path.is_file():
        fail(f"history file not found: {path}")

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        fail("history contains no samples")
    if len(lines) > MAX_HISTORY_SAMPLES:
        fail(f"history contains {len(lines)} samples; maximum is {MAX_HISTORY_SAMPLES}")

    samples: list[dict] = []
    for index, line in enumerate(lines, start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"line {index}: invalid JSON: {exc.msg}")
        if not isinstance(payload, dict):
            fail(f"line {index}: sample must be a JSON object")
        if payload.get("schema_version") != 1:
            fail(f"line {index}: schema_version must be 1")

        app_version = payload.get("app_version")
        source_revision = payload.get("source_revision")
        attempt = payload.get("attempt")
        latency = payload.get("listen_request_to_ready_ms")

        if not isinstance(app_version, str) or not app_version:
            fail(f"line {index}: app_version must be a non-empty string")
        if not isinstance(source_revision, str) or len(source_revision) != 40 or any(
            char not in "0123456789abcdefABCDEF" for char in source_revision
        ):
            fail(f"line {index}: source_revision must be a 40-character hex SHA")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            fail(f"line {index}: attempt must be an integer >= 1")
        if not isinstance(latency, int) or isinstance(latency, bool) or latency < 0:
            fail(f"line {index}: listen_request_to_ready_ms must be an integer >= 0")

        recorded_at = parse_utc(payload.get("recorded_at_utc"), index)
        samples.append(
            {
                "app_version": app_version,
                "source_revision": source_revision.lower(),
                "attempt": attempt,
                "latency_ms": latency,
                "recorded_at": recorded_at,
                "recorded_at_utc": payload["recorded_at_utc"],
            }
        )
    return samples


def nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        fail("cannot calculate percentile without samples")
    if percentile <= 0 or percentile > 1:
        fail("percentile must be in (0, 1]")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def build_summary(samples: list[dict], min_samples: int, expected_app: str | None, expected_source: str | None) -> dict:
    if min_samples < 1:
        fail("--min-samples must be >= 1")
    if len(samples) < min_samples:
        fail(f"history has {len(samples)} samples; need at least {min_samples}")

    app_versions = {sample["app_version"] for sample in samples}
    source_revisions = {sample["source_revision"] for sample in samples}
    if len(app_versions) != 1:
        fail("history mixes app_version identities")
    if len(source_revisions) != 1:
        fail("history mixes source_revision identities")

    app_version = next(iter(app_versions))
    source_revision = next(iter(source_revisions))
    if expected_app is not None and app_version != expected_app:
        fail(f"app_version mismatch: expected {expected_app}, got {app_version}")
    if expected_source is not None and source_revision != expected_source.lower():
        fail(f"source_revision mismatch: expected {expected_source.lower()}, got {source_revision}")

    latencies = [sample["latency_ms"] for sample in samples]
    median = statistics.median(latencies)
    ordered_by_time = sorted(samples, key=lambda sample: sample["recorded_at"])

    return {
        "schema_version": 1,
        "app_version": app_version,
        "source_revision": source_revision,
        "sample_count": len(samples),
        "first_recorded_at_utc": ordered_by_time[0]["recorded_at_utc"],
        "last_recorded_at_utc": ordered_by_time[-1]["recorded_at_utc"],
        "listen_request_to_ready_ms": {
            "min": min(latencies),
            "median": median,
            "p95_nearest_rank": nearest_rank(latencies, 0.95),
            "max": max(latencies),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize provenance-bound Raise AI voice startup history without inventing a product threshold."
    )
    parser.add_argument("history", type=Path, help="voice-startup-evidence.jsonl")
    parser.add_argument("--output", type=Path, help="optional JSON summary output path")
    parser.add_argument("--min-samples", type=int, default=1)
    parser.add_argument("--expect-app-version")
    parser.add_argument("--expect-source-revision")
    args = parser.parse_args()

    try:
        samples = load_history(args.history)
        summary = build_summary(
            samples,
            min_samples=args.min_samples,
            expected_app=args.expect_app_version,
            expected_source=args.expect_source_revision,
        )
    except ValueError as exc:
        print(f"VOICE-STARTUP-SUMMARY FAIL: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"VOICE-STARTUP-SUMMARY PASS: {summary['sample_count']} samples -> {args.output}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
