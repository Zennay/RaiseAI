#!/usr/bin/env python3
"""Validate provenance-bound Watch voice startup evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "schema_version",
    "recorded_at_utc",
    "app_version",
    "source_revision",
    "attempt",
    "listen_request_to_ready_ms",
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


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


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_evidence(
    payload: dict[str, Any],
    *,
    now: dt.datetime | None = None,
    max_age_seconds: int = 300,
    max_listen_ready_ms: int | None = None,
    expect_app_version: str | None = None,
    expect_source_revision: str | None = None,
) -> dict[str, Any]:
    _require(set(payload) == REQUIRED_FIELDS, "unexpected or missing evidence fields")
    _require(payload["schema_version"] == 1, "unsupported schema_version")

    recorded_at = _parse_timestamp(payload["recorded_at_utc"])
    now_utc = now or dt.datetime.now(dt.timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=dt.timezone.utc)
    else:
        now_utc = now_utc.astimezone(dt.timezone.utc)

    age_seconds = (now_utc - recorded_at).total_seconds()
    _require(age_seconds >= -30, "evidence timestamp is too far in the future")
    _require(age_seconds <= max_age_seconds, "evidence is stale")

    app_version = payload["app_version"]
    _require(isinstance(app_version, str) and 0 < len(app_version) <= 80, "invalid app_version")

    source_revision = payload["source_revision"]
    _require(
        isinstance(source_revision, str) and SHA40.fullmatch(source_revision) is not None,
        "source_revision must be a lowercase 40-character git SHA",
    )

    attempt = payload["attempt"]
    _require(_is_int(attempt) and attempt >= 1, "attempt must be an integer >= 1")

    latency_ms = payload["listen_request_to_ready_ms"]
    _require(
        _is_int(latency_ms) and 0 <= latency_ms <= 60_000,
        "listen_request_to_ready_ms must be an integer between 0 and 60000",
    )

    if max_listen_ready_ms is not None:
        _require(max_listen_ready_ms >= 0, "max_listen_ready_ms must be >= 0")
        _require(
            latency_ms <= max_listen_ready_ms,
            f"listen_request_to_ready_ms exceeds {max_listen_ready_ms} ms",
        )

    if expect_app_version is not None:
        _require(app_version == expect_app_version, "app_version does not match expected value")
    if expect_source_revision is not None:
        _require(
            source_revision == expect_source_revision,
            "source_revision does not match expected value",
        )

    return {
        "app_version": app_version,
        "source_revision": source_revision,
        "attempt": attempt,
        "listen_request_to_ready_ms": latency_ms,
        "age_seconds": max(0, int(age_seconds)),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="voice-startup-evidence.json")
    parser.add_argument("--max-age-seconds", type=int, default=300)
    parser.add_argument("--max-listen-ready-ms", type=int)
    parser.add_argument("--expect-app-version")
    parser.add_argument("--expect-source-revision")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    try:
        summary = validate_evidence(
            payload,
            max_age_seconds=args.max_age_seconds,
            max_listen_ready_ms=args.max_listen_ready_ms,
            expect_app_version=args.expect_app_version,
            expect_source_revision=args.expect_source_revision,
        )
    except EvidenceError as exc:
        raise SystemExit(f"voice startup evidence invalid: {exc}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
