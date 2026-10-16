#!/usr/bin/env python3
"""Permission-respecting Android-phone feasibility probe for official ChatGPT Voice.

This does NOT bridge Watch audio or enter ChatGPT Voice automatically. It only
checks an attached Android phone and optionally launches the installed official
app through the public launcher. Human timestamps are labelled observations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

OFFICIAL_PACKAGE = "com.openai.chatgpt"
SERIAL = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_OUTPUT = 16_384


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
        raise ProbeError("Official ChatGPT Android package not installed")
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
    parser.add_argument("--launch", action="store_true", help="explicitly launch the installed official ChatGPT app")
    parser.add_argument("--interactive", action="store_true", help="time manually observed app/Voice states; requires --launch")
    parser.add_argument("--evidence", type=Path, help="write private, new-only JSON measurements")
    args = parser.parse_args(argv)
    if args.interactive and not args.launch:
        parser.error("--interactive requires --launch")
    if args.evidence and not args.launch:
        parser.error("--evidence requires --launch")
    try:
        if not shutil.which(args.adb):
            raise ProbeError("ADB not found; install Android platform-tools first")
        serial = select_serial(args.adb, args.serial)
        phone = inspect_phone(args.adb, serial)
        result: dict[str, object] = {
            "schema_version": 1, "date_utc": utc_now(),
            "phone_model": phone["model"], "package": OFFICIAL_PACKAGE,
            "launch_requested": args.launch, "launch_command_ms": None,
            "operator_observations": {},
            "watch_microphone_bridge_verified": False,
            "watch_speaker_bridge_verified": False,
            "consumer_voice_api_claimed": False,
            "measurement_level": "ADB launcher observation, not physical Watch integration",
        }
        print(f"Phone: {phone['model']}; official ChatGPT installed.")
        if args.launch:
            start = time.monotonic()
            result["launch_command_ms"] = launch_official_app(args.adb, serial)
            print("Standard official-app launcher invoked. Voice is NOT opened automatically.")
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
