#!/usr/bin/env python3
"""Create an allowlisted, validated physical evidence share bundle (issue #514).

Usage: python3 tools/create-physical-share-bundle.py SESSION_DIRECTORY OUTPUT_DIRECTORY
Never attach the input directory to GitHub: it may contain watch identifiers or transcripts.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

FILES = {
    "e2e-result.json": ("valid", "answer_present"),
    "v1-result.json": ("v1_gate_passed",),
    "quality-result.json": ("valid", "quality_evidence_complete"),
}
MAX_BYTES = 64 * 1024
SENSITIVE = ("serial", "transcript", "answer", "token", "secret", "credential",
             "password", "authorization", "api_key", "api-key", "private_key")


class ShareError(ValueError):
    pass


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ShareError("duplicate JSON field")
        result[key] = value
    return result


def inspect(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized not in {"answer_present"} and any(term in normalized for term in SENSITIVE):
                raise ShareError("sensitive field found")
            inspect(child)
    elif isinstance(value, list):
        for item in value:
            inspect(item)


def read_safe(path: Path):
    if not hasattr(os, "O_NOFOLLOW"):
        raise ShareError("O_NOFOLLOW is required")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ShareError("not a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ShareError("file too large")
    finally:
        os.close(fd)
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ShareError("invalid JSON constant")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ShareError("invalid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ShareError("summary must be an object")
    inspect(data)
    return data


def bundle(source: Path, destination: Path):
    if not source.is_dir() or source.is_symlink():
        raise ShareError("source must be a directory, not a symlink")
    if destination.exists() or destination.is_symlink():
        raise ShareError("destination already exists")
    # Validate everything before creating any output.
    validated = {}
    for name, mandatory in FILES.items():
        payload = read_safe(source / name)
        if name != "e2e-result.json" and (type(payload.get("schema_version")) is not int or payload["schema_version"] != 1):
            raise ShareError(f"{name}: unsupported schema")
        if name == "e2e-result.json" and (payload.get("outcome") != "success" or payload.get("route") != "quick_ai"):
            raise ShareError("e2e-result.json: requires successful quick_ai")
        if any(payload.get(field) is not True for field in mandatory):
            raise ShareError(f"{name}: required PASS fields missing")
        validated[name] = payload
    e2e = validated["e2e-result.json"]
    v1 = validated["v1-result.json"].get("evidence_identity")
    quality = validated["quality-result.json"]
    if not isinstance(v1, dict):
        raise ShareError("v1-result.json: missing evidence identity")
    for field in ("app_version", "source_revision"):
        values = (e2e.get(field), v1.get(field), quality.get(field))
        if any(not isinstance(v, str) or not v for v in values) or len(set(values)) != 1:
            raise ShareError(f"mixed or missing physical evidence identity: {field}")
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        for name, payload in validated.items():
            target = destination / name
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(payload, output, indent=2, sort_keys=True, allow_nan=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
    except BaseException:
        for name in FILES:
            (destination / name).unlink(missing_ok=True)
        destination.rmdir()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_directory", type=Path)
    parser.add_argument("new_share_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        bundle(args.session_directory, args.new_share_directory)
    except (OSError, ShareError, ValueError) as exc:
        print(f"SHARE BUNDLE FAIL: {exc}", file=sys.stderr)
        return 1
    print("SHARE BUNDLE PASS: three validated summaries only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
