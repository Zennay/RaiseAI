#!/usr/bin/env python3
"""Read and atomically update physical-validation session metadata."""

from __future__ import annotations

import argparse
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
MUTABLE_FIELDS = {
    "e2e_passed": bool,
    "e2e_verified_at_utc": str,
    "v1_gate_passed": bool,
    "v1_verified_at_utc": str,
}


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


def _parse_value(field: str, raw_value: str) -> Any:
    expected_type = MUTABLE_FIELDS.get(field)
    if expected_type is None:
        raise SessionUpdateError(f"field is not mutable: {field}")
    if expected_type is bool:
        if raw_value == "true":
            return True
        if raw_value == "false":
            return False
        raise SessionUpdateError(f"{field} must be true or false")
    if not raw_value.strip():
        raise SessionUpdateError(f"{field} must be a non-empty string")
    if "\n" in raw_value or "\r" in raw_value:
        raise SessionUpdateError(f"{field} must be a single-line string")
    return raw_value


def update_session(path: Path, field: str, raw_value: str) -> None:
    payload, mode = _load_session(path)
    payload[field] = _parse_value(field, raw_value)
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--get", dest="get_field", choices=sorted(READABLE_FIELDS))
    action.add_argument("--set", dest="set_values", nargs=2, metavar=("FIELD", "VALUE"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.get_field is not None:
            print(read_session_field(args.session, args.get_field))
        else:
            field, value = args.set_values
            update_session(args.session, field, value)
    except SessionUpdateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
