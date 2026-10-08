#!/usr/bin/env python3
"""Create a fail-closed, three-file physical acceptance sharing directory.

Usage: python3 tools/create-physical-share-bundle.py SESSION_DIR OUTPUT_DIR
Keep the original session and raw evidence local. Only canonical summaries
are eligible for publication; this tool never modifies source evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

FILES = ("e2e-result.json", "v1-result.json", "quality-result.json")
MAX_BYTES = 64 * 1024
SECRET_KEY = re.compile(
    r"(serial|transcript|answer[_-]?text|response[_-]?text|"
    r"prompt|credential|secret|token|password|api[_-]?key|"
    r"authorization|cookie|raw[_-]?text)", re.I
)


class ShareError(ValueError):
    pass


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ShareError(why)


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate JSON key: " + key)
        obj[key] = value
    return obj


def reject_sensitive(value):
    if isinstance(value, dict):
        for key, item in value.items():
            require(not SECRET_KEY.search(key), "sensitive field: " + key)
            reject_sensitive(item)
    elif isinstance(value, list):
        for item in value:
            reject_sensitive(item)


def load_summary(directory_fd: int, name: str):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), name + " is not regular")
        require(info.st_size <= MAX_BYTES, name + " is too large")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, name + " is too large")
    finally:
        os.close(fd)
    payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                         parse_constant=lambda x: (_ for _ in ()).throw(ShareError("non-finite JSON: " + x)))
    require(isinstance(payload, dict), name + " must be an object")
    reject_sensitive(payload)
    return payload, raw


def validate(summaries):
    e2e, v1, quality = (summaries[name][0] for name in FILES)
    require(e2e.get("valid") is True and e2e.get("outcome") == "success"
            and e2e.get("route") == "quick_ai" and e2e.get("answer_present") is True,
            "E2E must be successful quick_ai with answer")
    require(v1.get("schema_version") == 1 and v1.get("v1_gate_passed") is True,
            "V1 reliability gate must pass")
    require(quality.get("schema_version") == 1 and quality.get("valid") is True
            and quality.get("quality_evidence_complete") is True,
            "physical observation quality must be complete")
    identity = v1.get("evidence_identity")
    require(isinstance(identity, dict), "missing V1 identity")
    for key in ("app_version", "source_revision"):
        require(isinstance(e2e.get(key), str) and e2e[key],
                "missing E2E identity " + key)
        require(e2e[key] == identity.get(key) == quality.get(key),
                "cross-summary identity mismatch: " + key)
    require(isinstance(quality.get("apk_sha256"), str)
            and len(quality["apk_sha256"]) == 64, "missing APK identity")
    for key in ("screen_off_tested", "background_tested", "ux_failures_reviewed"):
        require(quality.get(key) is True, "incomplete quality check: " + key)


def make_bundle(source: Path, target: Path):
    require(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
            "safe directory reads not supported")
    source_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        summaries = {name: load_summary(source_fd, name) for name in FILES}
        validate(summaries)
    finally:
        os.close(source_fd)
    # mkdir is exclusive: never reuse/overwrite a previous share bundle.
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        target_fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in FILES:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                fd = os.open(name, flags, 0o600, dir_fd=target_fd)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(summaries[name][1])
                    stream.flush()
                    os.fsync(stream.fileno())
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
    except Exception:
        # The exclusively-created directory contains only files we created.
        for name in FILES:
            try:
                (target / name).unlink()
            except FileNotFoundError:
                pass
        target.rmdir()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        make_bundle(args.session_dir, args.output_dir)
    except (OSError, ValueError, UnicodeError) as exc:
        print("SHARE BUNDLE REFUSED: " + str(exc), file=sys.stderr)
        return 1
    print("SAFE SHARE BUNDLE CREATED: " + str(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
