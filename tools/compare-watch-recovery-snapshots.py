#!/usr/bin/env python3
"""Compare provenance-bound Raise AI Watch recovery snapshots."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IDENTITY_FIELDS = (
    "watch_serial",
    "watch_model",
    "app_version",
    "source_revision",
    "installed_apk_sha256",
)


def _parse_time(value: Any, field: str) -> datetime:
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


def _hex(value: Any, length: int, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.lower().strip()
    if len(normalized) != length or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError(f"{field} must be exactly {length} hexadecimal characters")
    return normalized


def require_snapshot(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"{path}: unsupported schema_version")
    if data.get("read_only_capture") is not True:
        raise ValueError(f"{path}: snapshot is not marked read_only_capture")

    for field in (
        "captured_at_utc",
        "watch_serial",
        "watch_model",
        "app_version",
        "source_revision",
        "installed_apk_sha256",
        "boot_id",
        "uptime_seconds",
        "monitoring_enabled",
        "calibrated",
        "gesture_monitor_service_running",
    ):
        if field not in data:
            raise ValueError(f"{path}: missing {field}")

    _parse_time(data["captured_at_utc"], f"{path}: captured_at_utc")
    data["source_revision"] = _hex(data["source_revision"], 40, f"{path}: source_revision")
    data["installed_apk_sha256"] = _hex(
        data["installed_apk_sha256"],
        64,
        f"{path}: installed_apk_sha256",
    )

    boot_id = data["boot_id"]
    if not isinstance(boot_id, str) or len(boot_id.strip()) != 36:
        raise ValueError(f"{path}: boot_id must be a 36-character UUID string")

    uptime = data["uptime_seconds"]
    if not isinstance(uptime, (int, float)) or isinstance(uptime, bool) or uptime < 0:
        raise ValueError(f"{path}: uptime_seconds must be a non-negative number")

    for field in (
        "monitoring_enabled",
        "calibrated",
        "gesture_monitor_service_running",
    ):
        if not isinstance(data[field], bool):
            raise ValueError(f"{path}: {field} must be boolean")

    for field in ("watch_serial", "watch_model", "app_version"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(f"{path}: {field} must be non-empty")

    return data


def _require_active_monitoring(snapshot: dict[str, Any], when: str) -> None:
    if snapshot["monitoring_enabled"] is not True:
        raise ValueError(f"{when} snapshot does not have monitoring enabled")
    if snapshot["calibrated"] is not True:
        raise ValueError(f"{when} snapshot is not calibrated")
    if snapshot["gesture_monitor_service_running"] is not True:
        raise ValueError(f"{when} snapshot does not show GestureMonitorService running")


def compare(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    before_time = _parse_time(before["captured_at_utc"], "before captured_at_utc")
    after_time = _parse_time(after["captured_at_utc"], "after captured_at_utc")
    if after_time <= before_time:
        raise ValueError("after snapshot must be later than before snapshot")

    for field in ("watch_serial", "watch_model"):
        if before[field] != after[field]:
            raise ValueError(
                f"snapshot identity mismatch for {field}: "
                f"{before[field]!r} != {after[field]!r}"
            )

    _require_active_monitoring(before, "before")
    _require_active_monitoring(after, "after")

    if mode == "reboot":
        for field in ("app_version", "source_revision", "installed_apk_sha256"):
            if before[field] != after[field]:
                raise ValueError(
                    f"reboot recovery requires stable {field}: "
                    f"{before[field]!r} != {after[field]!r}"
                )
        if before["boot_id"].lower() == after["boot_id"].lower():
            raise ValueError("reboot recovery requires a different boot_id")
    elif mode == "package-update":
        if before["boot_id"].lower() != after["boot_id"].lower():
            raise ValueError("package-update recovery must be isolated from a Watch reboot")
        identity_changed = any(
            before[field] != after[field]
            for field in ("app_version", "source_revision", "installed_apk_sha256")
        )
        if not identity_changed:
            raise ValueError("package-update recovery requires a changed app/source/APK identity")
    else:
        raise ValueError(f"unsupported recovery mode: {mode}")

    duration_seconds = (after_time - before_time).total_seconds()
    return {
        "schema_version": 1,
        "recovery_valid": True,
        "mode": mode,
        "watch_serial": before["watch_serial"],
        "watch_model": before["watch_model"],
        "before": {
            "captured_at_utc": before["captured_at_utc"],
            "app_version": before["app_version"],
            "source_revision": before["source_revision"],
            "installed_apk_sha256": before["installed_apk_sha256"],
            "boot_id": before["boot_id"].lower(),
            "uptime_seconds": float(before["uptime_seconds"]),
        },
        "after": {
            "captured_at_utc": after["captured_at_utc"],
            "app_version": after["app_version"],
            "source_revision": after["source_revision"],
            "installed_apk_sha256": after["installed_apk_sha256"],
            "boot_id": after["boot_id"].lower(),
            "uptime_seconds": float(after["uptime_seconds"]),
        },
        "elapsed_seconds": round(duration_seconds, 3),
        "monitoring_enabled_after": True,
        "calibrated_after": True,
        "gesture_monitor_service_running_after": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("reboot", "package-update"),
        help="Recovery event proven by the two snapshots.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        result = compare(
            require_snapshot(args.before),
            require_snapshot(args.after),
            mode=args.mode,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(1, f"Recovery evidence invalid: {exc}\n")

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
