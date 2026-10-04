#!/usr/bin/env python3
"""Compare two read-only Raise AI Watch battery evidence snapshots."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} is not valid ISO-8601: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def require_snapshot(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"{path}: unsupported schema_version")
    if data.get("read_only_capture") is not True:
        raise ValueError(f"{path}: snapshot is not marked read_only_capture")
    for field in ("watch_serial", "watch_model", "app_version", "source_revision", "battery_percent", "plugged"):
        if field not in data:
            raise ValueError(f"{path}: missing {field}")
    percent = data["battery_percent"]
    if not isinstance(percent, (int, float)) or isinstance(percent, bool) or not 0 <= percent <= 100:
        raise ValueError(f"{path}: battery_percent must be between 0 and 100")
    revision = data["source_revision"]
    if not isinstance(revision, str) or len(revision) != 40 or any(c not in "0123456789abcdefABCDEF" for c in revision):
        raise ValueError(f"{path}: source_revision must be exactly 40 hexadecimal characters")
    if not isinstance(data["plugged"], int) or isinstance(data["plugged"], bool):
        raise ValueError(f"{path}: plugged must be an integer")
    parse_time(data.get("captured_at_utc"), f"{path}: captured_at_utc")
    return data


def compare(start: dict[str, Any], end: dict[str, Any], min_minutes: float) -> dict[str, Any]:
    identity_fields = ("watch_serial", "watch_model", "app_version", "source_revision")
    for field in identity_fields:
        if start[field] != end[field]:
            raise ValueError(f"snapshot identity mismatch for {field}: {start[field]!r} != {end[field]!r}")

    if start["plugged"] != 0 or end["plugged"] != 0:
        raise ValueError("battery drain evidence requires unplugged start and end snapshots")

    start_time = parse_time(start["captured_at_utc"], "start captured_at_utc")
    end_time = parse_time(end["captured_at_utc"], "end captured_at_utc")
    duration_seconds = (end_time - start_time).total_seconds()
    if duration_seconds <= 0:
        raise ValueError("end snapshot must be later than start snapshot")

    duration_minutes = duration_seconds / 60.0
    if duration_minutes < min_minutes:
        raise ValueError(
            f"measurement is too short: {duration_minutes:.1f} minutes < {min_minutes:.1f} minute minimum"
        )

    drop = float(start["battery_percent"]) - float(end["battery_percent"])
    if drop < 0:
        raise ValueError("battery percent increased while snapshots report unplugged state")

    hours = duration_seconds / 3600.0
    return {
        "schema_version": 1,
        "watch_serial": start["watch_serial"],
        "watch_model": start["watch_model"],
        "app_version": start["app_version"],
        "source_revision": start["source_revision"].lower(),
        "start_captured_at_utc": start["captured_at_utc"],
        "end_captured_at_utc": end["captured_at_utc"],
        "duration_minutes": round(duration_minutes, 3),
        "start_battery_percent": float(start["battery_percent"]),
        "end_battery_percent": float(end["battery_percent"]),
        "battery_drop_percentage_points": round(drop, 3),
        "battery_drop_pp_per_hour": round(drop / hours, 3),
        "measurement_valid": True,
        "min_duration_minutes": min_minutes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("start", type=Path)
    parser.add_argument("end", type=Path)
    parser.add_argument("--min-duration-minutes", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.min_duration_minutes <= 0:
        parser.error("--min-duration-minutes must be greater than zero")

    try:
        result = compare(
            require_snapshot(args.start),
            require_snapshot(args.end),
            args.min_duration_minutes,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(1, f"Battery evidence invalid: {exc}\n")

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
