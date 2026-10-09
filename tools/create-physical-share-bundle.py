#!/usr/bin/env python3
"""Prepare a conservative, secret-safe physical evidence share directory.

Only the three reviewed summary JSON files are copied. Raw session data, Watch
serials, transcripts, operator notes and diagnostics are never copied.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

NAMES = ("e2e-result.json", "v1-result.json", "quality-result.json")
LIMIT = 64 * 1024
SENSITIVE = ("serial", "transcript", "answer", "token", "password", "secret",
             "credential", "authorization", "api_key", "private_key", "prompt",
             "raw_audio", "device_id", "session_id")


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def safe_read(path: Path):
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("safe no-follow file reads unavailable")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise ValueError(f"{path.name}: input must be a bounded regular file")
        data = os.read(fd, LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError(f"{path.name}: oversized JSON")
    finally:
        os.close(fd)
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"nonfinite JSON number: {value}")))


def screen(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if any(word in normalized for word in SENSITIVE):
                raise ValueError(f"sensitive field forbidden: {key}")
            screen(child)
    elif isinstance(value, list):
        for child in value:
            screen(child)


def verify(name, document):
    if not isinstance(document, dict):
        raise ValueError(f"{name}: expected JSON object")
    screen(document)
    if name == "quality-result.json":
        if document.get("schema_version") != 1 or document.get("valid") is not True or document.get("quality_evidence_complete") is not True:
            raise ValueError("quality evidence has not passed validation")
    elif name == "v1-result.json":
        if document.get("schema_version") != 1 or document.get("v1_gate_passed") is not True:
            raise ValueError("V1 trial gate has not passed")
    else:
        if document.get("schema_version") != 2 or document.get("valid") is not True:
            raise ValueError("E2E evidence must have valid schema-v2 result")


def bundle(source: Path, target: Path):
    if not source.is_dir() or source.is_symlink():
        raise ValueError("source must be a real directory")
    payload = {}
    for name in NAMES:
        doc = safe_read(source / name)
        verify(name, doc)
        payload[name] = (json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    # Never touch an existing destination, including symlinks or broken links.
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        for name, data in payload.items():
            fd = os.open(target / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for name in NAMES:
            (target / name).unlink(missing_ok=True)
        target.rmdir()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_directory", type=Path)
    parser.add_argument("new_share_directory", type=Path)
    args = parser.parse_args()
    try:
        bundle(args.session_directory, args.new_share_directory)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"SHARE BUNDLE REJECTED: {exc}", file=sys.stderr)
        return 1
    print(f"SHARE BUNDLE READY: {args.new_share_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
