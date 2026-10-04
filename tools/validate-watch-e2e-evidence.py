#!/usr/bin/env python3
"""Validate secret-safe Raise AI Watch E2E evidence.

This validator is intentionally strict: evidence is accepted only when the
schema is exact, no unexpected fields are present, the record is fresh enough
when requested, and the recorded request matches the requested validation
constraints.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

KNOWN_ROUTES = {"quick_ai", "deep_ai", "current_info", "smart_home", "zcloud_task"}
COMMON_KEYS = {
    "schema_version",
    "recorded_at_utc",
    "outcome",
    "input_length_chars",
    "latency_ms",
}
SUCCESS_KEYS = COMMON_KEYS | {
    "route",
    "status",
    "execution_enabled",
    "execution_reason_present",
    "answer_present",
}
FAILURE_KEYS = COMMON_KEYS | {"error_code"}
MAX_FUTURE_SKEW_SECONDS = 60


class EvidenceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _parse_timestamp(value: Any) -> dt.datetime:
    _require(isinstance(value, str) and value, "recorded_at_utc must be a non-empty string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EvidenceError("recorded_at_utc must be ISO-8601") from exc
    _require(parsed.tzinfo is not None, "recorded_at_utc must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def validate_evidence(
    payload: Any,
    *,
    expect_route: str | None = None,
    expect_status: str | None = None,
    max_latency_ms: int | None = None,
    max_age_seconds: int | None = None,
    require_answer: bool = False,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    _require(isinstance(payload, dict), "evidence root must be a JSON object")
    _require(payload.get("schema_version") == 1, "schema_version must equal 1")

    outcome = payload.get("outcome")
    _require(outcome in {"success", "failure"}, "outcome must be success or failure")

    expected_keys = SUCCESS_KEYS if outcome == "success" else FAILURE_KEYS
    actual_keys = set(payload)
    unexpected = sorted(actual_keys - expected_keys)
    missing = sorted(expected_keys - actual_keys)
    _require(not unexpected, f"unexpected evidence fields: {', '.join(unexpected)}")
    _require(not missing, f"missing evidence fields: {', '.join(missing)}")

    recorded_at = _parse_timestamp(payload["recorded_at_utc"])

    if max_age_seconds is not None:
        _require(max_age_seconds >= 0, "max_age_seconds must be non-negative")
        now = now_utc or dt.datetime.now(dt.timezone.utc)
        _require(now.tzinfo is not None, "now_utc must include a timezone")
        age_seconds = (now.astimezone(dt.timezone.utc) - recorded_at).total_seconds()
        _require(
            age_seconds >= -MAX_FUTURE_SKEW_SECONDS,
            f"recorded_at_utc is more than {MAX_FUTURE_SKEW_SECONDS}s in the future",
        )
        _require(
            age_seconds <= max_age_seconds,
            f"evidence age {max(0, int(age_seconds))}s exceeds maximum {max_age_seconds}s",
        )

    input_length = payload["input_length_chars"]
    latency_ms = payload["latency_ms"]
    _require(type(input_length) is int and input_length >= 0, "input_length_chars must be a non-negative integer")
    _require(type(latency_ms) is int and latency_ms >= 0, "latency_ms must be a non-negative integer")

    if max_latency_ms is not None:
        _require(max_latency_ms >= 0, "max_latency_ms must be non-negative")
        _require(latency_ms <= max_latency_ms, f"latency_ms {latency_ms} exceeds maximum {max_latency_ms}")

    if outcome == "failure":
        error_code = payload["error_code"]
        _require(isinstance(error_code, str) and error_code, "error_code must be a non-empty string")
        raise EvidenceError(f"Watch E2E request failed: {error_code}")

    route = payload["route"]
    status = payload["status"]
    _require(isinstance(route, str) and route in KNOWN_ROUTES, f"unknown route: {route!r}")
    _require(isinstance(status, str) and status and status != "unknown", "status must be a known non-empty value")
    _require(input_length > 0, "successful evidence must record a non-empty input")
    for key in ("execution_enabled", "execution_reason_present", "answer_present"):
        _require(type(payload[key]) is bool, f"{key} must be boolean")

    if expect_route is not None:
        _require(route == expect_route, f"route {route!r} does not match expected {expect_route!r}")
    if expect_status is not None:
        _require(status == expect_status, f"status {status!r} does not match expected {expect_status!r}")
    if require_answer:
        _require(payload["answer_present"], "successful evidence did not contain an answer/message")

    return {
        "valid": True,
        "outcome": outcome,
        "route": route,
        "status": status,
        "latency_ms": latency_ms,
        "input_length_chars": input_length,
        "answer_present": payload["answer_present"],
        "execution_enabled": payload["execution_enabled"],
        "recorded_at_utc": payload["recorded_at_utc"],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="watch-e2e-evidence.json")
    parser.add_argument("--expect-route", choices=sorted(KNOWN_ROUTES))
    parser.add_argument("--expect-status")
    parser.add_argument("--max-latency-ms", type=int)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        help="reject evidence older than this many seconds (allows up to 60s future clock skew)",
    )
    parser.add_argument("--require-answer", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        payload = json.loads(args.evidence.read_text(encoding="utf-8"))
        result = validate_evidence(
            payload,
            expect_route=args.expect_route,
            expect_status=args.expect_status,
            max_latency_ms=args.max_latency_ms,
            max_age_seconds=args.max_age_seconds,
            require_answer=args.require_answer,
        )
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, separators=(",", ":")))
        return 1

    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
