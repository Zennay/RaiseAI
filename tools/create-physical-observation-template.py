#!/usr/bin/env python3
"""Create a fail-closed operator-observation template for a physical session."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

FUTURE_CLOCK_SKEW = dt.timedelta(minutes=5)

REQUIRED_SESSION_KEYS = {
    "schema_version",
    "watch_serial",
    "app_version",
    "source_revision",
    "apk_sha256",
    "started_at_utc",
}


class TemplateError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TemplateError(message)


def _parse_timestamp(value: Any, field: str) -> dt.datetime:
    _require(isinstance(value, str) and value.strip(), f"{field} must be a non-empty string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TemplateError(f"{field} must be ISO-8601") from exc
    _require(parsed.tzinfo is not None, f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _format_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def build_template(
    session: Any,
    *,
    recorded_at_utc: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    _require(isinstance(session, dict), "session root must be a JSON object")
    missing = sorted(REQUIRED_SESSION_KEYS - set(session))
    _require(not missing, f"session is missing required fields: {', '.join(missing)}")

    _require(
        type(session["schema_version"]) is int and session["schema_version"] == 1,
        "session schema_version must equal 1",
    )

    watch_serial = session["watch_serial"]
    app_version = session["app_version"]
    source_revision = session["source_revision"]
    apk_sha256 = session["apk_sha256"]
    _require(isinstance(watch_serial, str) and watch_serial.strip(), "session watch_serial must be non-empty")
    _require(isinstance(app_version, str) and app_version.strip(), "session app_version must be non-empty")
    _require(
        isinstance(source_revision, str)
        and len(source_revision) == 40
        and all(char in "0123456789abcdefABCDEF" for char in source_revision),
        "session source_revision must be a 40-character Git SHA",
    )
    _require(
        isinstance(apk_sha256, str)
        and len(apk_sha256) == 64
        and all(char in "0123456789abcdefABCDEF" for char in apk_sha256),
        "session apk_sha256 must be a 64-character SHA-256",
    )

    started_at = _parse_timestamp(session["started_at_utc"], "session started_at_utc")
    if now_utc is None:
        now = dt.datetime.now(dt.timezone.utc)
    else:
        _require(now_utc.tzinfo is not None, "now_utc must include a timezone")
        now = now_utc.astimezone(dt.timezone.utc)
    if recorded_at_utc is None:
        recorded_at = now.replace(microsecond=0)
    else:
        recorded_at = _parse_timestamp(recorded_at_utc, "recorded_at_utc")
    _require(
        recorded_at >= started_at,
        "recorded_at_utc must not be before the physical session started",
    )
    _require(
        recorded_at <= now + FUTURE_CLOCK_SKEW,
        "recorded_at_utc must not be more than 5 minutes in the future",
    )

    return {
        "schema_version": 1,
        "recorded_at_utc": _format_utc(recorded_at),
        "watch_serial": watch_serial,
        "app_version": app_version,
        "source_revision": source_revision.lower(),
        "apk_sha256": apk_sha256.lower(),
        "screen_off_tested": False,
        "screen_off_behavior": "",
        "background_tested": False,
        "background_behavior": "",
        "ux_failures_reviewed": False,
        "visible_ux_failures": [],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="physical-validation session.json")
    parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: operator-observations.json beside session.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    output = args.output or args.session.with_name("operator-observations.json")
    try:
        session = json.loads(args.session.read_text(encoding="utf-8"))
        payload = build_template(session)
        try:
            with output.open("x", encoding="utf-8") as output_file:
                output_file.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        except FileExistsError as exc:
            raise TemplateError(
                f"refusing to overwrite existing observation file: {output}"
            ) from exc
    except (OSError, json.JSONDecodeError, TemplateError) as exc:
        print(json.dumps({"created": False, "reason": str(exc)}, separators=(",", ":")))
        return 1

    print(json.dumps({"created": True, "path": str(output)}, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
