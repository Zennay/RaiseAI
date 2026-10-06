#!/usr/bin/env python3
"""Publish a completed physical-validation JSON result atomically and exclusively."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any


class ResultPublishError(ValueError):
    pass


def _load_source(source: Path) -> bytes:
    if source.is_symlink():
        raise ResultPublishError(f"refusing symlink result source: {source}")
    try:
        info = source.stat()
    except OSError as exc:
        raise ResultPublishError(f"cannot stat result source: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ResultPublishError(f"result source is not a regular file: {source}")
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise ResultPublishError(f"cannot read result source: {exc}") from exc
    if not payload:
        raise ResultPublishError("result source is empty")
    try:
        parsed: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResultPublishError(f"result source is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ResultPublishError("result JSON root must be an object")
    return payload


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


def publish_result(source: Path, destination: Path) -> None:
    payload = _load_source(source)
    if destination.is_symlink():
        raise ResultPublishError(f"refusing symlink result destination: {destination}")
    if destination.exists():
        raise ResultPublishError(f"refusing to overwrite existing result: {destination}")
    if not destination.parent.is_dir():
        raise ResultPublishError(f"result parent is not a directory: {destination.parent}")

    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            staged = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(staged, destination)
        except FileExistsError as exc:
            raise ResultPublishError(
                f"refusing to overwrite existing result: {destination}"
            ) from exc
        except OSError as exc:
            raise ResultPublishError(f"exclusive result publish failed: {exc}") from exc
        _fsync_directory(destination.parent)
    finally:
        if staged is not None:
            try:
                staged.unlink()
            except FileNotFoundError:
                pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        publish_result(args.source, args.destination)
    except ResultPublishError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
