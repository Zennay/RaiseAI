#!/usr/bin/env python3
"""Validate explicit physical-session quality observations for Raise AI.

The physical V1 gate already has machine checks for provenance, E2E and gesture
reliability. This validator closes the separate evidence-completeness gap for
human-observable behavior required by issue #34: screen-off/background behavior
and visible UX failures must be explicitly reviewed and bound to the same
Watch/app/source/APK session. It does not claim that those observations passed a
product threshold; it only prevents them from being omitted or mixed across
sessions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

OBSERVATION_KEYS = {
    "schema_version",
    "recorded_at_utc",
    "watch_serial",
    "app_version",
    "source_revision",
    "apk_sha256",
    "screen_off_tested",
    "screen_off_behavior",
    "background_tested",
    "background_behavior",
    "ux_failures_reviewed",
    "visible_ux_failures",
}


class ObservationError(ValueError):
    pass


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ObservationError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _strict_json_loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_reject_duplicate_object_pairs)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ObservationError(message)


def _parse_timestamp(value: Any, field: str) -> dt.datetime:
    _require(isinstance(value, str) and value.strip(), f"{field} must be a non-empty string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ObservationError(f"{field} must be ISO-8601") from exc
    _require(parsed.tzinfo is not None, f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _format_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _require_sha(value: Any, field: str, length: int) -> str:
    _require(isinstance(value, str), f"{field} must be a string")
    normalized = value.strip().lower()
    _require(
        len(normalized) == length and all(char in "0123456789abcdef" for char in normalized),
        f"{field} must be exactly {length} hexadecimal characters",
    )
    return normalized


def validate_observations(session: Any, observations: Any) -> dict[str, Any]:
    _require(isinstance(session, dict), "session root must be a JSON object")
    _require(isinstance(observations, dict), "observations root must be a JSON object")
    _require(
        type(observations.get("schema_version")) is int and observations["schema_version"] == 1,
        "schema_version must equal 1",
    )
    _require(
        type(session.get("schema_version")) is int and session["schema_version"] == 1,
        "session schema_version must equal 1",
    )

    actual_keys = set(observations)
    missing = sorted(OBSERVATION_KEYS - actual_keys)
    unexpected = sorted(actual_keys - OBSERVATION_KEYS)
    _require(not missing, f"missing observation fields: {', '.join(missing)}")
    _require(not unexpected, f"unexpected observation fields: {', '.join(unexpected)}")

    for key in ("watch_serial", "app_version", "source_revision", "apk_sha256", "started_at_utc"):
        _require(key in session, f"session is missing {key}")

    watch_serial = observations["watch_serial"]
    app_version = observations["app_version"]
    _require(isinstance(watch_serial, str) and watch_serial.strip(), "watch_serial must be non-empty")
    _require(isinstance(app_version, str) and app_version.strip(), "app_version must be non-empty")

    source_revision = _require_sha(observations["source_revision"], "source_revision", 40)
    apk_sha256 = _require_sha(observations["apk_sha256"], "apk_sha256", 64)
    expected_revision = _require_sha(session["source_revision"], "session source_revision", 40)
    expected_apk = _require_sha(session["apk_sha256"], "session apk_sha256", 64)

    _require(watch_serial == session["watch_serial"], "watch_serial does not match physical session")
    _require(app_version == session["app_version"], "app_version does not match physical session")
    _require(source_revision == expected_revision, "source_revision does not match physical session")
    _require(apk_sha256 == expected_apk, "apk_sha256 does not match physical session")

    recorded_at = _parse_timestamp(observations["recorded_at_utc"], "recorded_at_utc")
    started_at = _parse_timestamp(session["started_at_utc"], "session started_at_utc")
    _require(recorded_at >= started_at, "observations were recorded before the physical session started")

    for key in ("screen_off_tested", "background_tested", "ux_failures_reviewed"):
        _require(type(observations[key]) is bool, f"{key} must be boolean")
        _require(observations[key], f"{key} must be true before the quality evidence is complete")

    for key in ("screen_off_behavior", "background_behavior"):
        value = observations[key]
        _require(isinstance(value, str) and value.strip(), f"{key} must be a non-empty observation")
        _require(len(value.strip()) <= 1000, f"{key} must be at most 1000 characters")

    failures = observations["visible_ux_failures"]
    _require(isinstance(failures, list), "visible_ux_failures must be a JSON array")
    _require(len(failures) <= 50, "visible_ux_failures must contain at most 50 entries")
    normalized_failures: list[str] = []
    for index, item in enumerate(failures):
        _require(
            isinstance(item, str) and item.strip(),
            f"visible_ux_failures[{index}] must be a non-empty string",
        )
        text = item.strip()
        _require(len(text) <= 500, f"visible_ux_failures[{index}] must be at most 500 characters")
        normalized_failures.append(text)

    return {
        "valid": True,
        "quality_evidence_complete": True,
        "recorded_at_utc": _format_utc(recorded_at),
        "watch_identity_match": True,
        "app_version": app_version,
        "source_revision": source_revision,
        "apk_sha256": apk_sha256,
        "screen_off_tested": True,
        "background_tested": True,
        "ux_failures_reviewed": True,
        "visible_ux_failure_count": len(normalized_failures),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="physical-validation session.json")
    parser.add_argument("observations", type=Path, help="operator-observations.json")
    parser.add_argument("--output", type=Path, help="optional secret-safe quality-result.json path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        session = _strict_json_loads(args.session.read_text(encoding="utf-8"))
        observations = _strict_json_loads(args.observations.read_text(encoding="utf-8"))
        result = validate_observations(session, observations)
        if args.output is not None:
            try:
                with args.output.open("x", encoding="utf-8") as output_file:
                    output_file.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
            except FileExistsError as exc:
                raise ObservationError(
                    f"refusing to overwrite existing quality result: {args.output}"
                ) from exc
    except (OSError, json.JSONDecodeError, ObservationError) as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, separators=(",", ":")))
        return 1

    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
