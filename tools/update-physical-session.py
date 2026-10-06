#!/usr/bin/env python3
"""Read physical-validation state and commit gate outcomes atomically."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

READABLE_FIELDS = {
    "app_version": str,
    "source_revision": str,
    "watch_serial": str,
    "e2e_passed": bool,
}
GATES = {"e2e", "v1"}
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class SessionUpdateError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SessionUpdateError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_session(path: Path) -> tuple[dict[str, Any], int]:
    if path.is_symlink():
        raise SessionUpdateError(f"refusing symlink session metadata: {path}")
    try:
        file_stat = path.stat()
    except OSError as exc:
        raise SessionUpdateError(f"cannot stat session metadata: {exc}") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise SessionUpdateError(f"session metadata is not a regular file: {path}")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionUpdateError(f"cannot read valid session JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SessionUpdateError("session root must be a JSON object")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise SessionUpdateError("session schema_version must equal 1")
    return payload, stat.S_IMODE(file_stat.st_mode)


def _parse_utc_timestamp(name: str, value: Any) -> dt.datetime:
    if not isinstance(value, str):
        raise SessionUpdateError(f"{name} must be a canonical UTC timestamp")
    try:
        parsed = dt.datetime.strptime(value, TIMESTAMP_FORMAT)
    except ValueError as exc:
        raise SessionUpdateError(
            f"{name} must use canonical UTC form YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def _require_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if type(value) is not bool:
        raise SessionUpdateError(f"{field} must be boolean")
    return value


def read_session_field(path: Path, field: str) -> str:
    expected_type = READABLE_FIELDS.get(field)
    if expected_type is None:
        raise SessionUpdateError(f"field is not readable: {field}")
    payload, _ = _load_session(path)
    if field not in payload:
        raise SessionUpdateError(f"session is missing {field}")
    value = payload[field]
    if expected_type is bool:
        if type(value) is not bool:
            raise SessionUpdateError(f"{field} must be boolean")
        return "true" if value else "false"
    if not isinstance(value, str) or not value.strip():
        raise SessionUpdateError(f"{field} must be a non-empty string")
    if "\n" in value or "\r" in value:
        raise SessionUpdateError(f"{field} must be a single-line string")
    return value


def _write_session(path: Path, payload: dict[str, Any], mode: int) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            os.fchmod(handle.fileno(), mode)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                try:
                    os.fsync(directory_fd)
                except OSError:
                    pass
            finally:
                os.close(directory_fd)
    except OSError as exc:
        raise SessionUpdateError(f"atomic session update failed: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def mark_gate_passed(path: Path, gate: str, verified_at_utc: str) -> None:
    if gate not in GATES:
        raise SessionUpdateError(f"unknown physical validation gate: {gate}")

    payload, mode = _load_session(path)
    started_at = _parse_utc_timestamp("started_at_utc", payload.get("started_at_utc"))
    verified_at = _parse_utc_timestamp("verified_at_utc", verified_at_utc)
    if verified_at < started_at:
        raise SessionUpdateError("verified_at_utc cannot precede started_at_utc")

    e2e_passed = _require_bool(payload, "e2e_passed")
    v1_passed = _require_bool(payload, "v1_gate_passed")
    has_e2e_time = "e2e_verified_at_utc" in payload
    has_v1_time = "v1_verified_at_utc" in payload
    if e2e_passed != has_e2e_time:
        raise SessionUpdateError("E2E gate flag/timestamp state is incoherent")
    if v1_passed != has_v1_time:
        raise SessionUpdateError("V1 gate flag/timestamp state is incoherent")
    if v1_passed and not e2e_passed:
        raise SessionUpdateError("V1 gate cannot be committed without E2E")

    if gate == "e2e":
        if e2e_passed or "e2e_verified_at_utc" in payload:
            raise SessionUpdateError("E2E gate is already committed for this session")
        payload["e2e_passed"] = True
        payload["e2e_verified_at_utc"] = verified_at_utc
    else:
        if not e2e_passed:
            raise SessionUpdateError("cannot commit V1 before the E2E gate")
        e2e_verified = _parse_utc_timestamp(
            "e2e_verified_at_utc", payload.get("e2e_verified_at_utc")
        )
        if verified_at < e2e_verified:
            raise SessionUpdateError("V1 verification cannot precede E2E verification")
        if v1_passed or "v1_verified_at_utc" in payload:
            raise SessionUpdateError("V1 gate is already committed for this session")
        payload["v1_gate_passed"] = True
        payload["v1_verified_at_utc"] = verified_at_utc

    _write_session(path, payload, mode)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--get", dest="get_field", choices=sorted(READABLE_FIELDS))
    action.add_argument(
        "--mark-passed",
        dest="mark_passed",
        nargs=2,
        metavar=("GATE", "VERIFIED_AT_UTC"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.get_field is not None:
            print(read_session_field(args.session, args.get_field))
        else:
            gate, verified_at = args.mark_passed
            mark_gate_passed(args.session, gate, verified_at)
    except SessionUpdateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
