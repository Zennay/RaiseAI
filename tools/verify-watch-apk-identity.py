#!/usr/bin/env python3
"""Verify a prebuilt Raise AI Watch APK before physical evidence collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path


DEX_SCAN_CHUNK_BYTES = 64 * 1024
EXECUTABLE_DEX_NAME = re.compile(r"^classes(?:[2-9]|[1-9][0-9]+)?[.]dex$")


class ApkIdentityError(ValueError):
    pass


def _normalize_sha(value: str, *, label: str, length: int) -> str:
    normalized = value.strip().lower()
    if len(normalized) != length or not re.fullmatch(r"[0-9a-f]+", normalized):
        raise ApkIdentityError(f"{label} must be a {length}-character lowercase/uppercase hex value")
    return normalized


def _sha256_open_file(apk_file) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = apk_file.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _zip_member_contains(
    archive: zipfile.ZipFile,
    name: str,
    needle: bytes,
) -> bool:
    """Search one ZIP member without materializing the full decompressed file."""
    overlap = b""
    keep = max(0, len(needle) - 1)

    with archive.open(name, "r") as member:
        while True:
            chunk = member.read(DEX_SCAN_CHUNK_BYTES)
            if not chunk:
                return False

            window = overlap + chunk
            if needle in window:
                return True

            overlap = window[-keep:] if keep else b""


def verify_apk(
    path: Path,
    *,
    expected_source_revision: str,
    expected_sha256: str | None = None,
    expected_abi: str | None = "armeabi-v7a",
) -> dict[str, object]:
    revision = _normalize_sha(
        expected_source_revision,
        label="expected source revision",
        length=40,
    )
    expected_digest = (
        _normalize_sha(expected_sha256, label="expected APK SHA-256", length=64)
        if expected_sha256 is not None
        else None
    )

    if not hasattr(os, "O_NOFOLLOW"):
        raise ApkIdentityError("safe no-follow APK reads are unavailable on this platform")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ApkIdentityError(f"APK cannot be opened safely: {path}") from exc

    with os.fdopen(fd, "rb", closefd=True) as apk_file:
        metadata = os.fstat(apk_file.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ApkIdentityError(f"APK must be a regular file: {path}")

        digest = _sha256_open_file(apk_file)
        if expected_digest is not None and digest != expected_digest:
            raise ApkIdentityError(
                f"APK SHA-256 mismatch: expected {expected_digest}, got {digest}"
            )

        try:
            apk_file.seek(0)
            with zipfile.ZipFile(apk_file) as archive:
                names = archive.namelist()
                dex_files = sorted(name for name in names if EXECUTABLE_DEX_NAME.fullmatch(name))
                if not dex_files:
                    raise ApkIdentityError("APK contains no DEX files")

                needle = revision.encode("ascii")
                revision_hits = [
                    name
                    for name in dex_files
                    if _zip_member_contains(archive, name, needle)
                ]
                if not revision_hits:
                    raise ApkIdentityError(
                        "expected source revision is not embedded in APK DEX"
                    )

                abis = sorted(
                    {
                        parts[1]
                        for name in names
                        if name.startswith("lib/") and name.endswith(".so")
                        for parts in [name.split("/")]
                        if len(parts) >= 3 and parts[1]
                    }
                )
        except zipfile.BadZipFile as exc:
            raise ApkIdentityError("APK is not a valid ZIP/APK archive") from exc

    if expected_abi is not None:
        if abis != [expected_abi]:
            rendered = ", ".join(abis) if abis else "<none>"
            raise ApkIdentityError(
                f"APK ABI set mismatch: expected only {expected_abi}, got {rendered}"
            )

    return {
        "valid": True,
        "apk_sha256": digest,
        "source_revision": revision,
        "revision_dex_files": revision_hits,
        "abis": abis,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--expect-source-revision", required=True)
    parser.add_argument("--expect-sha256")
    parser.add_argument("--expect-abi", default="armeabi-v7a")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = verify_apk(
            args.apk,
            expected_source_revision=args.expect_source_revision,
            expected_sha256=args.expect_sha256,
            expected_abi=args.expect_abi,
        )
    except ApkIdentityError as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, separators=(",", ":")))
        return 2

    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
