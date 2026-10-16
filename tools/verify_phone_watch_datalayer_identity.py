#!/usr/bin/env python3
"""Read-only, fail-closed signed-APK compatibility preflight for Wear Data Layer.

This checks same application ID and same signing certificate. It does NOT
authenticate the APK publisher, prove pairing, start apps or bridge ChatGPT audio.
"""
from __future__ import annotations

import argparse
import hmac
from pathlib import Path
import re
import shutil
import subprocess
import sys

EXPECTED_PACKAGE = "nl.zennay.raiseai"
MAX_APK_BYTES = 200_000_000
DIGEST = re.compile(r"^[a-fA-F0-9]{64}$")
PACKAGE = re.compile(r"^package: name='([^']+)'", re.MULTILINE)
SIGNER = re.compile(r"^Signer #[0-9]+ certificate SHA-256 digest:[ \t]*([^\r\n]+)$", re.MULTILINE)


class CompatibilityError(Exception):
    pass


def checked_apk(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise CompatibilityError("APK missing or symlinked")
    size = path.stat().st_size
    if not 0 < size <= MAX_APK_BYTES:
        raise CompatibilityError("APK outside allowed size budget")
    return path


def checked_command(executable: str, args: list[str], timeout: int = 30) -> str:
    if not shutil.which(executable):
        raise CompatibilityError("Required Android Build-Tools executable not found")
    try:
        result = subprocess.run(
            [executable, *args], timeout=timeout, capture_output=True,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CompatibilityError(f"Android tools failed: {type(error).__name__}") from error
    if result.returncode != 0:
        raise CompatibilityError("Android APK verification tool returned nonzero")
    return result.stdout[:16_384]


def package_name(output: str) -> str:
    values = PACKAGE.findall(output)
    if len(values) != 1 or values[0] != EXPECTED_PACKAGE:
        raise CompatibilityError("APK is not the expected Raise AI application ID")
    return values[0]


def signer_digest(output: str) -> str:
    values = SIGNER.findall(output)
    if len(values) != 1:
        raise CompatibilityError("APK signer set missing or ambiguous")
    fingerprint = values[0].replace(":", "").strip().lower()
    if not DIGEST.fullmatch(fingerprint):
        raise CompatibilityError("APK signing digest malformed")
    return fingerprint


def inspect_apk(path: Path, aapt: str, apksigner: str) -> tuple[str, str]:
    checked_apk(path)
    info = checked_command(aapt, ["dump", "badging", str(path)])
    signature = checked_command(apksigner, ["verify", "--print-certs", str(path)])
    return package_name(info), signer_digest(signature)


def preflight(phone: Path, watch: Path, aapt: str, apksigner: str) -> None:
    if phone.absolute() == watch.absolute():
        raise CompatibilityError("Must use two distinct phone and Watch APK files")
    phone_package, phone_signer = inspect_apk(phone, aapt, apksigner)
    watch_package, watch_signer = inspect_apk(watch, aapt, apksigner)
    if phone_package != watch_package or not hmac.compare_digest(phone_signer, watch_signer):
        raise CompatibilityError("Phone and Watch package/signing identity mismatch")
    print("PASS: phone and Watch APK application IDs and single active signing certificates match.")
    print("NOT PROVEN: APK publisher, installed-device identity, real Data Layer transport, or ChatGPT Voice audio.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phone-apk", type=Path, required=True)
    parser.add_argument("--watch-apk", type=Path, required=True)
    parser.add_argument("--aapt", default="aapt")
    parser.add_argument("--apksigner", default="apksigner")
    args = parser.parse_args(argv)
    try:
        preflight(args.phone_apk, args.watch_apk, args.aapt, args.apksigner)
        return 0
    except (OSError, CompatibilityError) as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
