#!/usr/bin/env python3
"""Publish and resolve the latest physical-validation session pointer safely."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path


class PointerError(ValueError):
    pass


def _require_regular_file(path: Path, label: str) -> os.stat_result:
    if path.is_symlink():
        raise PointerError(f"refusing symlink {label}: {path}")
    try:
        info = path.stat()
    except OSError as exc:
        raise PointerError(f"cannot stat {label}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise PointerError(f"{label} is not a regular file: {path}")
    return info


def _canonical_session(session_dir: Path, evidence_root: Path) -> Path:
    try:
        root = evidence_root.resolve(strict=True)
        session = session_dir.resolve(strict=True)
    except OSError as exc:
        raise PointerError(f"cannot resolve evidence/session path: {exc}") from exc
    if not root.is_dir():
        raise PointerError(f"evidence root is not a directory: {root}")
    if not session.is_dir():
        raise PointerError(f"physical session is not a directory: {session}")
    try:
        relative = session.relative_to(root)
    except ValueError as exc:
        raise PointerError(f"physical session escapes evidence root: {session}") from exc
    if relative == Path("."):
        raise PointerError("physical session must be a child of the evidence root")
    _require_regular_file(session / "session.json", "session metadata")
    return session


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            pass
    finally:
        os.close(fd)


def publish_latest(pointer: Path, session_dir: Path, evidence_root: Path) -> Path:
    session = _canonical_session(session_dir, evidence_root)
    if pointer.is_symlink():
        raise PointerError(f"refusing symlink latest-session pointer: {pointer}")

    mode = 0o600
    if pointer.exists():
        info = _require_regular_file(pointer, "latest-session pointer")
        mode = stat.S_IMODE(info.st_mode)

    pointer.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=pointer.parent,
            prefix=f".{pointer.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            os.fchmod(handle.fileno(), mode)
            handle.write(str(session) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, pointer)
        temp_path = None
        _fsync_directory(pointer.parent)
    except OSError as exc:
        raise PointerError(f"atomic latest-session publish failed: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
    return session


def resolve_latest(pointer: Path, evidence_root: Path) -> Path:
    _require_regular_file(pointer, "latest-session pointer")
    try:
        raw = pointer.read_text(encoding="utf-8")
    except OSError as exc:
        raise PointerError(f"cannot read latest-session pointer: {exc}") from exc
    if "\r" in raw or "\x00" in raw:
        raise PointerError("latest-session pointer contains invalid control characters")
    value = raw[:-1] if raw.endswith("\n") else raw
    if not value or "\n" in value:
        raise PointerError("latest-session pointer must contain exactly one non-empty path")
    session_path = Path(value)
    if not session_path.is_absolute():
        raise PointerError("latest-session pointer must contain an absolute path")
    return _canonical_session(session_path, evidence_root)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish = subparsers.add_parser("publish")
    publish.add_argument("pointer", type=Path)
    publish.add_argument("session_dir", type=Path)
    publish.add_argument("evidence_root", type=Path)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("pointer", type=Path)
    resolve.add_argument("evidence_root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "publish":
            session = publish_latest(args.pointer, args.session_dir, args.evidence_root)
        else:
            session = resolve_latest(args.pointer, args.evidence_root)
    except PointerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
