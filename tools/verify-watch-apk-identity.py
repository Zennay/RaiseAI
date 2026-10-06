#!/usr/bin/env python3
"""Verify a prebuilt Raise AI Watch APK before physical evidence collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path


class ApkIdentityError(ValueError):
    pass


def _normalize_sha(value: str, *, label: str, length: int) -> str:
    normalized = value.strip().lower()
    if len(normalized) != length or not re.fullmatch(r"[0-9a-f]+", normalized):
        raise ApkIdentityError(f"{label} must be a {length}-character lowercase/uppercase hex value")
    return normalized


def verify_apk(
    path: Path,
    *,
    expected_source_revision: str,
    expected_sha256: str | None = None,
    expected_abi: str | None = "armeabi-v7a",
) -> dict[str, object]:
    if not path.is_file():
        raise ApkIdentityError(f"APK not found: {path}")

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

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise ApkIdentityError(
            f"APK SHA-256 mismatch: expected {expected_digest}, got {digest}"
        )

    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            duplicate_names = sorted(
                name for name, count in Counter(names).items() if count > 1
            )
            if duplicate_names:
                raise ApkIdentityError(
                    "APK contains duplicate ZIP entries: " + ", ".join(duplicate_names)
                )

            dex_files = sorted(
                name
                for name in names
                if re.fullmatch(r"classes(?:[2-9]|[1-9][0-9]+)?\.dex", name)
            )
            if not dex_files:
                raise ApkIdentityError("APK contains no root classes*.dex files")

            needle = revision.encode("ascii")
            revision_hits = [
                name for name in dex_files if needle in archive.read(name)
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
