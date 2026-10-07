#!/usr/bin/env python3
"""Prepare the canonical secret-safe physical acceptance share bundle."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 128 * 1024
MAX_E2E_LATENCY_MS = 15_000
APP_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
FROZEN_APP_VERSION = "1.5.2"
FROZEN_SOURCE_REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
FROZEN_APK_SHA256 = "3593ed2a952b575dd20e1c37629b88b09b455db5baaddc8a973cf5578511f391"
FROZEN_DETECTOR_CONFIG = (
    "raise-detector-v1;"
    "similarity=0.955;"
    "rearmSimilarity=0.9;"
    "movement=0.85;"
    "holdMs=200;"
    "movementWindowMs=1400;"
    "movementBurstMs=700;"
    "movementHits=2;"
    "approachStart=0.92;"
    "approachWindowMs=1900;"
    "minimumApproachRise=0.025;"
    "cooldownMs=2500;"
    "rearmHoldMs=500"
)
SUMMARY_FILES = ("e2e-result.json", "v1-result.json", "quality-result.json")
E2E_KEYS = {
    "valid",
    "outcome",
    "route",
    "status",
    "latency_ms",
    "input_length_chars",
    "answer_present",
    "execution_enabled",
    "recorded_at_utc",
    "app_version",
    "source_revision",
}
V1_KEYS = {
    "schema_version",
    "v1_gate_passed",
    "evidence_identity",
    "requirements",
    "results",
    "remaining",
    "rejected_trial_count",
}
QUALITY_KEYS = {
    "schema_version",
    "valid",
    "quality_evidence_complete",
    "recorded_at_utc",
    "watch_identity_match",
    "app_version",
    "source_revision",
    "apk_sha256",
    "screen_off_tested",
    "background_tested",
    "ux_failures_reviewed",
    "visible_ux_failure_count",
}
V1_IDENTITY_KEYS = {"app_version", "source_revision", "detector_config"}
V1_REQUIREMENT_KEYS = {
    "mouth_raise_trials",
    "non_trigger_trials",
    "min_detection_rate",
    "max_false_trigger_rate",
}
V1_RESULT_KEYS = {
    "mouth_raise_trials",
    "mouth_raise_detected",
    "detection_rate",
    "non_trigger_trials",
    "false_triggers",
    "false_trigger_rate",
}
V1_REMAINING_KEYS = {"mouth_raise_trials", "non_trigger_trials"}

SENSITIVE_KEYS = {
    "watch_serial",
    "transcript",
    "transcript_text",
    "answer",
    "answer_text",
    "response",
    "response_text",
    "token",
    "access_token",
    "api_key",
    "credential",
    "credentials",
    "gateway_token",
    "authorization",
}


class ShareBundleError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ShareBundleError(message)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str) -> Any:
    _require(hasattr(os, "O_NOFOLLOW"), "safe no-follow reads are unavailable on this platform")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ShareBundleError(f"{label} cannot be opened safely: {exc}") from exc

    try:
        metadata = os.fstat(fd)
        _require(stat.S_ISREG(metadata.st_mode), f"{label} must be a regular file")
        _require(metadata.st_size <= MAX_JSON_BYTES, f"{label} exceeds {MAX_JSON_BYTES} bytes")
        chunks: list[bytes] = []
        remaining = MAX_JSON_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(8192, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        _require(len(raw) <= MAX_JSON_BYTES, f"{label} exceeds {MAX_JSON_BYTES} bytes")
    finally:
        os.close(fd)

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ShareBundleError(f"{label} must be valid UTF-8") from exc

    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ShareBundleError(f"{label} must contain valid JSON") from exc


def _scan_sensitive_keys(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _require(isinstance(key, str), f"{path} contains a non-string JSON key")
            normalized = key.strip().lower().replace("-", "_")
            _require(normalized not in SENSITIVE_KEYS, f"{path} contains forbidden field {key!r}")
            _scan_sensitive_keys(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_sensitive_keys(nested, path=f"{path}[{index}]")


def _require_timestamp(value: Any, field: str) -> str:
    _require(isinstance(value, str) and value.endswith("Z"), f"{field} must be a canonical UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ShareBundleError(f"{field} must be ISO-8601") from exc
    _require(parsed.tzinfo is not None, f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _require_sha(value: Any, field: str, length: int = 40) -> str:
    _require(isinstance(value, str), f"{field} must be a string")
    normalized = value.strip().lower()
    _require(
        len(normalized) == length and all(char in "0123456789abcdef" for char in normalized),
        f"{field} must be a {length}-character hexadecimal value",
    )
    return normalized


def validate_summaries(
    e2e: Any,
    v1: Any,
    quality: Any,
) -> dict[str, dict[str, Any]]:
    for label, payload in (("e2e-result.json", e2e), ("v1-result.json", v1), ("quality-result.json", quality)):
        _require(isinstance(payload, dict), f"{label} root must be a JSON object")
        _scan_sensitive_keys(payload, path=label)

    expected_keys = {
        "e2e-result.json": E2E_KEYS,
        "v1-result.json": V1_KEYS,
        "quality-result.json": QUALITY_KEYS,
    }
    for label, payload in (("e2e-result.json", e2e), ("v1-result.json", v1), ("quality-result.json", quality)):
        missing = sorted(expected_keys[label] - set(payload))
        unexpected = sorted(set(payload) - expected_keys[label])
        _require(not missing, f"{label} missing fields: {', '.join(missing)}")
        _require(not unexpected, f"{label} unexpected fields: {', '.join(unexpected)}")

    _require(e2e.get("valid") is True, "e2e-result.json must declare valid=true")
    _require(e2e.get("outcome") == "success", "e2e-result.json must declare outcome=success")
    _require(e2e.get("route") == "quick_ai", "e2e-result.json must prove the quick_ai route")
    _require(e2e.get("status") == "answered", "e2e-result.json must declare status=answered")
    _require(e2e.get("answer_present") is True, "e2e-result.json must prove an answer was present")
    _require(
        type(e2e.get("latency_ms")) is int
        and 0 <= e2e["latency_ms"] <= MAX_E2E_LATENCY_MS,
        f"e2e-result.json latency_ms must be between 0 and {MAX_E2E_LATENCY_MS}",
    )
    _require(type(e2e.get("input_length_chars")) is int and e2e["input_length_chars"] > 0, "e2e-result.json input_length_chars must be a positive integer")
    _require(type(e2e.get("execution_enabled")) is bool, "e2e-result.json execution_enabled must be boolean")
    _require_timestamp(e2e.get("recorded_at_utc"), "e2e recorded_at_utc")

    _require(type(v1.get("schema_version")) is int and v1["schema_version"] == 1, "v1-result.json schema_version must equal 1")
    _require(v1.get("v1_gate_passed") is True, "v1-result.json must declare v1_gate_passed=true")
    identity = v1.get("evidence_identity")
    _require(isinstance(identity, dict), "v1-result.json evidence_identity must be an object")
    missing_identity = sorted(V1_IDENTITY_KEYS - set(identity))
    unexpected_identity = sorted(set(identity) - V1_IDENTITY_KEYS)
    _require(not missing_identity, f"v1-result.json evidence_identity missing fields: {', '.join(missing_identity)}")
    _require(not unexpected_identity, f"v1-result.json evidence_identity unexpected fields: {', '.join(unexpected_identity)}")
    for field, expected in (
        ("requirements", V1_REQUIREMENT_KEYS),
        ("results", V1_RESULT_KEYS),
        ("remaining", V1_REMAINING_KEYS),
    ):
        nested = v1.get(field)
        _require(isinstance(nested, dict), f"v1-result.json {field} must be an object")
        missing_nested = sorted(expected - set(nested))
        unexpected_nested = sorted(set(nested) - expected)
        _require(not missing_nested, f"v1-result.json {field} missing fields: {', '.join(missing_nested)}")
        _require(not unexpected_nested, f"v1-result.json {field} unexpected fields: {', '.join(unexpected_nested)}")

    requirements = v1["requirements"]
    _require(type(requirements["mouth_raise_trials"]) is int, "V1 mouth_raise_trials requirement must be an integer")
    _require(type(requirements["non_trigger_trials"]) is int, "V1 non_trigger_trials requirement must be an integer")
    _require(type(requirements["min_detection_rate"]) is float, "V1 min_detection_rate requirement must be a float")
    _require(type(requirements["max_false_trigger_rate"]) is float, "V1 max_false_trigger_rate requirement must be a float")
    _require(requirements["mouth_raise_trials"] == 30, "V1 must require exactly 30 mouth raises")
    _require(requirements["non_trigger_trials"] == 100, "V1 must require exactly 100 non-trigger trials")
    _require(requirements["min_detection_rate"] == 0.90, "V1 minimum detection rate must equal 0.90")
    _require(requirements["max_false_trigger_rate"] == 0.05, "V1 maximum false-trigger rate must equal 0.05")

    results = v1["results"]
    for key in ("mouth_raise_trials", "mouth_raise_detected", "non_trigger_trials", "false_triggers"):
        _require(type(results[key]) is int and results[key] >= 0, f"V1 {key} must be a non-negative integer")
    for key in ("detection_rate", "false_trigger_rate"):
        _require(type(results[key]) in (int, float), f"V1 {key} must be numeric")
        _require(0 <= results[key] <= 1, f"V1 {key} must be between 0 and 1")
    _require(results["mouth_raise_trials"] >= 30, "V1 result must contain at least 30 mouth raises")
    _require(results["non_trigger_trials"] >= 100, "V1 result must contain at least 100 non-trigger trials")
    _require(
        results["mouth_raise_detected"] <= results["mouth_raise_trials"],
        "V1 detected mouth raises cannot exceed mouth raise trials",
    )
    _require(
        results["false_triggers"] <= results["non_trigger_trials"],
        "V1 false triggers cannot exceed non-trigger trials",
    )
    expected_detection_rate = round(
        results["mouth_raise_detected"] / results["mouth_raise_trials"],
        6,
    )
    expected_false_trigger_rate = round(
        results["false_triggers"] / results["non_trigger_trials"],
        6,
    )
    _require(
        results["detection_rate"] == expected_detection_rate,
        "V1 detection_rate is inconsistent with detected/trial counts",
    )
    _require(
        results["false_trigger_rate"] == expected_false_trigger_rate,
        "V1 false_trigger_rate is inconsistent with false-trigger/trial counts",
    )
    _require(results["detection_rate"] >= 0.90, "V1 detection rate must meet 0.90")
    _require(results["false_trigger_rate"] <= 0.05, "V1 false-trigger rate must meet 0.05")

    remaining = v1["remaining"]
    _require(type(remaining["mouth_raise_trials"]) is int, "V1 mouth raise remainder must be an integer")
    _require(type(remaining["non_trigger_trials"]) is int, "V1 non-trigger remainder must be an integer")
    _require(remaining["mouth_raise_trials"] == 0, "V1 mouth raise remainder must be zero")
    _require(remaining["non_trigger_trials"] == 0, "V1 non-trigger remainder must be zero")
    _require(type(v1.get("rejected_trial_count")) is int and v1["rejected_trial_count"] >= 0, "V1 rejected_trial_count must be a non-negative integer")

    detector_config = identity.get("detector_config")
    _require(
        isinstance(detector_config, str)
        and 0 < len(detector_config) <= 400
        and "," not in detector_config
        and all(0x20 <= ord(char) <= 0x7E for char in detector_config),
        "V1 detector_config must be a printable comma-free identifier up to 400 characters",
    )
    _require(
        detector_config == FROZEN_DETECTOR_CONFIG,
        "V1 detector_config does not match the frozen v1.5.2 carrier",
    )

    _require(
        type(quality.get("schema_version")) is int and quality["schema_version"] == 1,
        "quality-result.json schema_version must equal 1",
    )
    _require(quality.get("valid") is True, "quality-result.json must declare valid=true")
    _require(quality.get("watch_identity_match") is True, "quality-result.json must declare watch_identity_match=true")
    _require(
        quality.get("quality_evidence_complete") is True,
        "quality-result.json must declare quality_evidence_complete=true",
    )
    for key in ("screen_off_tested", "background_tested", "ux_failures_reviewed"):
        _require(quality.get(key) is True, f"quality-result.json must declare {key}=true")
    _require_timestamp(quality.get("recorded_at_utc"), "quality recorded_at_utc")
    _require(
        type(quality.get("visible_ux_failure_count")) is int and quality["visible_ux_failure_count"] >= 0,
        "quality-result.json visible_ux_failure_count must be a non-negative integer",
    )

    app_version = e2e.get("app_version")
    _require(
        isinstance(app_version, str) and APP_VERSION_RE.fullmatch(app_version) is not None,
        "shared app_version must be canonical MAJOR.MINOR.PATCH",
    )
    _require(app_version == FROZEN_APP_VERSION, "shared app_version does not match frozen v1.5.2")
    _require(identity.get("app_version") == app_version, "V1 app_version does not match E2E summary")
    _require(quality.get("app_version") == app_version, "quality app_version does not match E2E summary")

    revision = _require_sha(e2e.get("source_revision"), "e2e source_revision")
    _require(revision == FROZEN_SOURCE_REVISION, "source_revision does not match frozen v1.5.2 carrier")
    _require(_require_sha(identity.get("source_revision"), "V1 source_revision") == revision, "V1 source_revision does not match E2E summary")
    _require(_require_sha(quality.get("source_revision"), "quality source_revision") == revision, "quality source_revision does not match E2E summary")
    apk_sha256 = _require_sha(quality.get("apk_sha256"), "quality apk_sha256", 64)
    _require(apk_sha256 == FROZEN_APK_SHA256, "quality apk_sha256 does not match frozen v1.5.2 carrier")

    return {
        "e2e-result.json": e2e,
        "v1-result.json": v1,
        "quality-result.json": quality,
    }


def prepare_bundle(session_dir: Path, output_dir: Path) -> None:
    try:
        session_stat = session_dir.lstat()
    except OSError as exc:
        raise ShareBundleError(f"session directory cannot be inspected safely: {exc}") from exc
    _require(not stat.S_ISLNK(session_stat.st_mode), "session directory must not be a symlink")
    _require(stat.S_ISDIR(session_stat.st_mode), f"session directory not found: {session_dir}")
    _require(not output_dir.exists() and not output_dir.is_symlink(), f"refusing to overwrite existing output: {output_dir}")
    try:
        output_parent_stat = output_dir.parent.lstat()
    except OSError as exc:
        raise ShareBundleError(f"output parent cannot be inspected safely: {exc}") from exc
    _require(not stat.S_ISLNK(output_parent_stat.st_mode), "output parent must not be a symlink")
    _require(stat.S_ISDIR(output_parent_stat.st_mode), f"output parent does not exist: {output_dir.parent}")

    loaded = {
        name: _load_json(session_dir / name, name)
        for name in SUMMARY_FILES
    }
    summaries = validate_summaries(
        loaded["e2e-result.json"],
        loaded["v1-result.json"],
        loaded["quality-result.json"],
    )

    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        os.chmod(stage, stat.S_IRWXU)
        for name in SUMMARY_FILES:
            target = stage / name
            serialized = json.dumps(summaries[name], indent=2, sort_keys=True) + "\n"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            fd = os.open(target, flags, stat.S_IRUSR | stat.S_IWUSR)
            try:
                os.write(fd, serialized.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)

        try:
            os.mkdir(output_dir, stat.S_IRWXU)
        except FileExistsError as exc:
            raise ShareBundleError(f"refusing to overwrite existing output: {output_dir}") from exc

        try:
            for name in SUMMARY_FILES:
                os.replace(stage / name, output_dir / name)
        except Exception:
            shutil.rmtree(output_dir, ignore_errors=True)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path, help="physical validation session directory")
    parser.add_argument("output_dir", type=Path, help="new directory for the canonical share bundle")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        prepare_bundle(args.session_dir, args.output_dir)
    except (OSError, ShareBundleError) as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, separators=(",", ":")))
        return 1

    print(
        json.dumps(
            {
                "valid": True,
                "bundle": str(args.output_dir),
                "files": list(SUMMARY_FILES),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
