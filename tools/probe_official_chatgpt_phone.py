#!/usr/bin/env python3
"""Permission-respecting Android-phone feasibility probe for official ChatGPT Voice.

This does NOT bridge Watch audio or enter ChatGPT Voice automatically. It only
checks an attached Android phone and optionally launches the installed official
app through the public launcher. Human timestamps are labelled observations.
"""
from __future__ import annotations

import argparse
import hmac
from datetime import datetime, timezone
import json
import tempfile
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time

OFFICIAL_PACKAGE = "com.openai.chatgpt"
SERIAL = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_OUTPUT = 16_384
MAX_BASE_APK_BYTES = 200_000_000
SIGNER_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class ProbeError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def adb_call(adb: str, args: list[str], timeout: int = 12) -> str:
    try:
        proc = subprocess.run(
            [adb, *args], check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProbeError(f"ADB command unavailable/timed out: {type(error).__name__}") from error
    if proc.returncode != 0:
        raise ProbeError(f"ADB command failed (exit={proc.returncode}); check phone authorisation")
    return proc.stdout[:MAX_OUTPUT]


def base_apk_path(pm_paths: str) -> str:
    """Find one safe, regular Android app base.apk path (not split APKs)."""
    # splitlines() would silently erase a forged carriage return in a package path.
    if any(ord(ch) < 32 and ch != "\n" for ch in pm_paths):
        raise ProbeError("Android package paths contain forbidden control characters")
    matches: list[str] = []
    for line in pm_paths.splitlines():
        if not line.startswith("package:"):
            continue
        path = line[len("package:"):]
        if (len(path) > 512 or not path.startswith("/") or
                not re.fullmatch(r"/[a-zA-Z0-9_./+~=:-]+", path)):
            raise ProbeError("Invalid Android package APK path")
        parts = PurePosixPath(path).parts
        if ".." in path.split("/") or len(parts) < 4:
            raise ProbeError("Unsafe Android package APK path")
        if parts[-1] == "base.apk":
            if not (path.startswith("/data/app/") or
                    path.startswith("/mnt/expand/")):
                raise ProbeError("Unexpected Android package APK directory")
            matches.append(path)
    if len(matches) != 1:
        raise ProbeError("Exactly one installed base.apk required for signature verification")
    return matches[0]


def extract_apksigner_sha256(output: str) -> str:
    """Require exactly one signer certificate SHA-256, never an ambiguous signer set."""
    values = re.findall(r"^Signer #[0-9]+ certificate SHA-256 digest:\s*(.+)$", output, re.M)
    if len(values) != 1:
        raise ProbeError("APK signer certificate unavailable or ambiguous")
    digest = values[0].strip().replace(":", "").lower()
    if not SIGNER_SHA256.fullmatch(digest):
        raise ProbeError("APK signer certificate fingerprint malformed")
    return digest


def verify_signing_certificate(
    adb: str, serial: str, expected_sha256: str, apksigner: str = "apksigner"
) -> None:
    """Attest locally pulled package signer against a user-supplied trusted SHA-256.

    This is NOT an independently maintained OpenAI trust registry. The expected digest
    must come from an independently authenticated publisher record, not from this phone.
    """
    if not SIGNER_SHA256.fullmatch(expected_sha256):
        raise ProbeError("Expected signer fingerprint must contain exactly 64 hex digits")
    if not shutil.which(apksigner):
        raise ProbeError("Android Build-Tools apksigner is required for APK signature verification")
    prefix = ["-s", serial, "shell"]
    apk_path = base_apk_path(adb_call(adb, prefix + ["pm", "path", OFFICIAL_PACKAGE]))
    size = adb_call(adb, prefix + ["stat", "-c", "%s", apk_path]).strip()
    if not size.isascii() or not size.isdecimal():
        raise ProbeError("Could not establish trusted APK size")
    if not 0 < int(size) <= MAX_BASE_APK_BYTES:
        raise ProbeError("APK size outside bounded attestation budget")

    with tempfile.TemporaryDirectory(prefix="raise-phone-signature-") as workdir:
        apk = Path(workdir) / "base.apk"
        try:
            pull = subprocess.run(
                [adb, "-s", serial, "pull", apk_path, str(apk)],
                check=False, capture_output=True, text=True, timeout=90
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProbeError(f"ADB signature read failed: {type(error).__name__}") from error
        if (pull.returncode != 0 or not apk.is_file() or
                not 0 < apk.stat().st_size <= MAX_BASE_APK_BYTES):
            raise ProbeError("Android APK retrieval failed or exceeded size budget")
        try:
            verified = subprocess.run(
                [apksigner, "verify", "--print-certs", str(apk)],
                check=False, capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProbeError(f"APK signature verification failed: {type(error).__name__}") from error
        if verified.returncode != 0:
            raise ProbeError("Installed APK did not pass apksigner verification")
        observed = extract_apksigner_sha256(verified.stdout[:MAX_OUTPUT])
        if not hmac.compare_digest(observed, expected_sha256.lower()):
            raise ProbeError("Installed APK signer does not match supplied trusted publisher SHA-256")


def select_serial(adb: str, requested: str | None) -> str:
    devices = adb_call(adb, ["devices"])
    connected: list[str] = []
    for line in devices.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            if not SERIAL.fullmatch(fields[0]):
                raise ProbeError("ADB reported an invalid device identifier")
            connected.append(fields[0])
    if requested and not SERIAL.fullmatch(requested):
        raise ProbeError("Invalid --serial")
    if requested:
        if requested not in connected:
            raise ProbeError("Requested authorised device not connected")
        return requested
    if len(connected) != 1:
        raise ProbeError("Exactly one authorised device required; otherwise supply --serial")
    return connected[0]


def inspect_phone(adb: str, serial: str) -> dict[str, str]:
    prefix = ["-s", serial, "shell"]
    watch = adb_call(adb, prefix + ["pm", "has-feature", "android.hardware.type.watch"]).strip()
    if watch != "false":
        raise ProbeError("Target is a Watch or the phone classification could not be verified")
    package = adb_call(adb, prefix + ["pm", "path", OFFICIAL_PACKAGE])
    if not any(line.startswith("package:") for line in package.splitlines()):
        raise ProbeError("ChatGPT Android package name not installed")
    model = adb_call(adb, prefix + ["getprop", "ro.product.model"]).strip()
    if not model or len(model) > 128 or any(ord(c) < 32 for c in model):
        raise ProbeError("Could not read a safe Android phone model")
    return {"model": model, "chatgpt_package": OFFICIAL_PACKAGE}


def launch_official_app(adb: str, serial: str) -> float:
    # Public, package-scoped Android MAIN/LAUNCHER intent only. Unlike
    # 'monkey', am start does not inject a random tap or other user event.
    # No private component, cookies or undocumented Voice URI.
    start = time.monotonic()
    output = adb_call(adb, [
        "-s", serial, "shell", "am", "start",
        "-a", "android.intent.action.MAIN",
        "-c", "android.intent.category.LAUNCHER",
        "-p", OFFICIAL_PACKAGE,
    ], timeout=20)
    elapsed = (time.monotonic() - start) * 1000
    if "Error:" in output or not (
        "Starting: Intent" in output or "Warning: Activity not started" in output
    ):
        raise ProbeError("Android did not confirm a standard public launcher start")
    return round(elapsed, 1)


def observed_step(prompt: str, start: float) -> dict[str, object]:
    # Human-observed timing only; this does not instrument microphone or audio.
    input(prompt + " [Enter when observed, Ctrl-C to cancel] ")
    return {"timestamp_utc": utc_now(), "elapsed_ms_since_launch": round((time.monotonic() - start) * 1000, 1)}


def evidence_write(path: Path, payload: dict[str, object]) -> None:
    # New private file only. Never overwrite an existing or linked evidence file.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="ADB device serial (required when multiple devices present)")
    parser.add_argument("--adb", default="adb", help="ADB executable (default: adb)")
    parser.add_argument("--expected-signer-sha256",
        help="optional known-good official publisher certificate SHA-256 from an independent trusted source; requires apksigner")
    parser.add_argument("--apksigner", default="apksigner", help="Android SDK Build-Tools apksigner executable")
    parser.add_argument("--launch", action="store_true", help="explicitly launch the installed official ChatGPT app")
    parser.add_argument("--interactive", action="store_true", help="time manually observed app/Voice states; requires --launch")
    parser.add_argument("--evidence", type=Path, help="write private, new-only JSON measurements")
    args = parser.parse_args(argv)
    if args.expected_signer_sha256 is not None and not SIGNER_SHA256.fullmatch(args.expected_signer_sha256):
        parser.error("--expected-signer-sha256 must be exactly 64 hexadecimal digits")
    if args.interactive and not args.launch:
        parser.error("--interactive requires --launch")
    if args.evidence and not args.launch:
        parser.error("--evidence requires --launch")
    try:
        if not shutil.which(args.adb):
            raise ProbeError("ADB not found; install Android platform-tools first")
        serial = select_serial(args.adb, args.serial)
        phone = inspect_phone(args.adb, serial)
        if args.expected_signer_sha256 is not None:
            verify_signing_certificate(args.adb, serial, args.expected_signer_sha256, args.apksigner)
        result: dict[str, object] = {
            "schema_version": 1, "date_utc": utc_now(),
            "phone_model": phone["model"], "package": OFFICIAL_PACKAGE,
            "launch_requested": args.launch, "launch_command_ms": None,
            "publisher_signature_verified": args.expected_signer_sha256 is not None,
            "operator_observations": {},
            "watch_microphone_bridge_verified": False,
            "watch_speaker_bridge_verified": False,
            "consumer_voice_api_claimed": False,
            "measurement_level": "ADB launcher observation, not physical Watch integration",
        }
        print(f"Phone: {phone['model']}; package {OFFICIAL_PACKAGE} present.")
        if args.expected_signer_sha256 is not None:
            print("APK signer verified against the supplied independent publisher certificate SHA-256.")
        else:
            print("Verify publisher/signature using a trusted source; package name alone is NOT authenticity proof.")
        if args.launch:
            start = time.monotonic()
            result["launch_command_ms"] = launch_official_app(args.adb, serial)
            print("Standard package launcher invoked. Voice is NOT opened automatically.")
            if args.interactive:
                print("On phone, open Voice using the OFFICIAL ChatGPT app UI.")
                obs: dict[str, object] = {}
                obs["voice_listening_phone"] = observed_step("Official Voice visually listening on phone?", start)
                obs["spoken_reply_phone"] = observed_step("Spoken ChatGPT Voice reply audible on phone?", start)
                result["operator_observations"] = obs
                result["measurement_level"] = "manual phone-only observation; Watch audio NOT checked"
            if args.evidence:
                evidence_write(args.evidence, result)
                print(f"Private evidence saved to: {args.evidence}")
        if args.expected_signer_sha256 is None:
            print("NOT PROVEN: official app signing, Watch-to-phone mic bridge, Watch speaker route, or automatic Voice start.")
        else:
            print("NOT PROVEN: Watch-to-phone mic bridge, Watch speaker route, or automatic Voice start.")
        return 0
    except (ProbeError, OSError) as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("Cancelled: no successful voice result recorded.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
