#!/usr/bin/env python3
"""Analyze provenance-bound Android process-exit evidence for Raise AI."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ENTRY_START = re.compile(r"^\s*ApplicationExitInfo #\d+:\s*$")
TIMESTAMP = re.compile(r"^\s*timestamp=(.+?)\s*$")
PROCESS = re.compile(r"^\s*process=(.+?)\s*$")
REASON = re.compile(r"^\s*reason=(\d+)\s+\((.+)\)\s*$")
STATUS = re.compile(r"^\s*status=(-?\d+)\s*$")
DESCRIPTION = re.compile(r"^\s*description=(.*?)\s*$")

# Android ApplicationExitInfo reasons that directly represent an app-side
# reliability failure for the V4 "no critical crash / stuck state" gate.
CRITICAL_REASON_CODES = {
    4: "REASON_CRASH",
    5: "REASON_CRASH_NATIVE",
    6: "REASON_ANR",
    7: "REASON_INITIALIZATION_FAILURE",
    9: "REASON_EXCESSIVE_RESOURCE_USAGE",
}


def parse_iso_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("session start must include a timezone")
    return parsed.astimezone(timezone.utc)


def parse_offset(value: str) -> timezone:
    if not re.fullmatch(r"[+-]\d{4}", value):
        raise ValueError("device UTC offset must look like +0100 or -0500")
    sign = 1 if value[0] == "+" else -1
    hours = int(value[1:3])
    minutes = int(value[3:5])
    if hours > 23 or minutes > 59:
        raise ValueError("invalid device UTC offset")
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def parse_device_timestamp(value: str, device_tz: timezone) -> datetime:
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S.%f")
    except ValueError as exc:
        raise ValueError(f"invalid dumpsys timestamp: {value}") from exc
    return parsed.replace(tzinfo=device_tz).astimezone(timezone.utc)


def parse_entries(text: str, *, device_tz: timezone) -> list[dict[str, Any]]:
    if "ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)" not in text:
        raise ValueError("input is not an Android activity exit-info dump")

    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] | None = None

    for line in lines:
        if ENTRY_START.match(line):
            if current:
                blocks.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current:
        blocks.append(current)

    entries: list[dict[str, Any]] = []
    for block in blocks:
        event: dict[str, Any] = {}
        for line in block:
            if match := TIMESTAMP.match(line):
                event["timestamp_raw"] = match.group(1).strip()
                event["timestamp_utc"] = parse_device_timestamp(
                    event["timestamp_raw"], device_tz
                ).isoformat().replace("+00:00", "Z")
            elif match := PROCESS.match(line):
                event["process"] = match.group(1).strip()
            elif match := REASON.match(line):
                event["reason_code"] = int(match.group(1))
                event["reason_label"] = match.group(2).strip()
            elif match := STATUS.match(line):
                event["status"] = int(match.group(1))
            elif match := DESCRIPTION.match(line):
                event["description"] = match.group(1).strip()

        required = ("timestamp_utc", "process", "reason_code", "reason_label", "status")
        missing = [field for field in required if field not in event]
        if missing:
            raise ValueError(
                "exit-info entry missing required fields: " + ", ".join(missing)
            )
        event.setdefault("description", None)
        entries.append(event)

    return entries


def analyze(
    text: str,
    *,
    session_start: str,
    device_utc_offset: str,
    package: str,
    watch_serial: str,
    watch_model: str,
    app_version: str,
    source_revision: str,
    installed_apk_sha256: str,
    service_running: bool,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        raise ValueError("source revision must be a 40-character Git SHA")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", installed_apk_sha256):
        raise ValueError("installed APK SHA-256 must be 64 hexadecimal characters")
    if not package.strip():
        raise ValueError("package must be non-empty")

    start = parse_iso_utc(session_start)
    device_tz = parse_offset(device_utc_offset)
    entries = parse_entries(text, device_tz=device_tz)

    scoped: list[dict[str, Any]] = []
    for event in entries:
        process = event["process"]
        if process != package and not process.startswith(package + ":"):
            continue
        event_time = parse_iso_utc(event["timestamp_utc"])
        if event_time < start:
            continue
        item = dict(event)
        item["critical"] = item["reason_code"] in CRITICAL_REASON_CODES
        if item["critical"]:
            item["critical_reason"] = CRITICAL_REASON_CODES[item["reason_code"]]
        scoped.append(item)

    critical = [event for event in scoped if event["critical"]]
    return {
        "schema_version": 1,
        "stability_valid": len(critical) == 0 and service_running,
        "captured_scope": "ApplicationExitInfo records at/after session start",
        "session_started_at_utc": start.isoformat().replace("+00:00", "Z"),
        "device_utc_offset": device_utc_offset,
        "package": package,
        "watch_serial": watch_serial,
        "watch_model": watch_model,
        "app_version": app_version,
        "source_revision": source_revision.lower(),
        "installed_apk_sha256": installed_apk_sha256.lower(),
        "gesture_monitor_service_running": service_running,
        "scoped_exit_count": len(scoped),
        "critical_exit_count": len(critical),
        "critical_reasons": sorted(
            {event["critical_reason"] for event in critical}
        ),
        "events": scoped,
        "limitations": [
            "ApplicationExitInfo is historical OS evidence, not a proof that every possible crash source is retained forever.",
            "This result covers the physical-validation session window represented by the supplied session start.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exit_info", type=Path)
    parser.add_argument("--session-start", required=True)
    parser.add_argument("--device-utc-offset", required=True)
    parser.add_argument("--package", default="nl.zennay.raiseai")
    parser.add_argument("--watch-serial", required=True)
    parser.add_argument("--watch-model", required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--installed-apk-sha256", required=True)
    parser.add_argument(
        "--service-running",
        choices=("true", "false"),
        required=True,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        result = analyze(
            args.exit_info.read_text(encoding="utf-8"),
            session_start=args.session_start,
            device_utc_offset=args.device_utc_offset,
            package=args.package,
            watch_serial=args.watch_serial,
            watch_model=args.watch_model,
            app_version=args.app_version,
            source_revision=args.source_revision,
            installed_apk_sha256=args.installed_apk_sha256,
            service_running=args.service_running == "true",
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Stability evidence invalid: {exc}\n")

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["stability_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
