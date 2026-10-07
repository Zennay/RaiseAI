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
import os
import re
import secrets
import stat
import sys
import tempfile
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
MAX_JSON_BYTES = 64 * 1024
MAX_FUTURE_SKEW_SECONDS = 60
APP_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ObservationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ObservationError(message)


def _reject_duplicate_json_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json_document(path: Path, label: str) -> Any:
    _require(
        hasattr(os, "O_NOFOLLOW"),
        f"{label} cannot be read safely on this platform",
    )
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    fd = os.open(path, flags)
    try:
        metadata = os.fstat(fd)
        _require(stat.S_ISREG(metadata.st_mode), f"{label} must be a regular file")
        _require(
            metadata.st_size <= MAX_JSON_BYTES,
            f"{label} exceeds maximum size of {MAX_JSON_BYTES} bytes",
        )

        chunks: list[bytes] = []
        remaining = MAX_JSON_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(8192, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        _require(
            len(raw) <= MAX_JSON_BYTES,
            f"{label} exceeds maximum size of {MAX_JSON_BYTES} bytes",
        )
    finally:
        os.close(fd)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ObservationError(f"{label} must be valid UTF-8") from exc

    return json.loads(text, object_pairs_hook=_reject_duplicate_json_fields)


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


def validate_observations(
    session: Any,
    observations: Any,
    *,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
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
    _require(
        isinstance(app_version, str) and APP_VERSION_RE.fullmatch(app_version) is not None,
        "app_version must be canonical MAJOR.MINOR.PATCH",
    )

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

    now = now_utc or dt.datetime.now(dt.timezone.utc)
    _require(now.tzinfo is not None, "now_utc must include a timezone")
    age_seconds = (now.astimezone(dt.timezone.utc) - recorded_at).total_seconds()
    _require(
        age_seconds >= -MAX_FUTURE_SKEW_SECONDS,
        f"recorded_at_utc is more than {MAX_FUTURE_SKEW_SECONDS}s in the future",
    )

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
        "schema_version": 1,
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


def write_new_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _require(path.name not in {"", ".", ".."}, "quality result path must name a file")
    _require(
        hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW"),
        "quality result directory cannot be verified safely on this platform",
    )

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC

    directory_fd = os.open(path.parent, directory_flags)
    temp_name: str | None = None
    published = False
    try:
        metadata = os.fstat(directory_fd)
        _require(stat.S_ISDIR(metadata.st_mode), "quality result parent must be a directory")

        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            create_flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            create_flags |= os.O_NOFOLLOW

        for _ in range(32):
            candidate = f".{path.name}.{secrets.token_hex(8)}.tmp"
            try:
                output_fd = os.open(
                    candidate,
                    create_flags,
                    stat.S_IRUSR | stat.S_IWUSR,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            temp_name = candidate
            break
        else:
            raise ObservationError("could not allocate a secure temporary quality result")

        with os.fdopen(output_fd, "w", encoding="utf-8") as output_file:
            output_file.write(serialized)
            output_file.flush()
            os.fsync(output_file.fileno())

        try:
            os.link(
                temp_name,
                path.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise ObservationError(
                f"refusing to overwrite existing quality result: {path}"
            ) from exc
        published = True
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            except OSError:
                if not published:
                    raise
        os.close(directory_fd)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="physical-validation session.json")
    parser.add_argument("observations", type=Path, help="operator-observations.json")
    parser.add_argument("--output", type=Path, help="optional secret-safe quality-result.json path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        session = load_json_document(args.session, "session")
        observations = load_json_document(args.observations, "observations")
        result = validate_observations(session, observations)
        if args.output is not None:
            write_new_json_atomically(args.output, result)
    except (OSError, json.JSONDecodeError, ObservationError) as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, separators=(",", ":")))
        return 1

    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
