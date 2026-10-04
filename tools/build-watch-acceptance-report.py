#!/usr/bin/env python3
"""Build a provenance-bound Raise AI physical acceptance report.

The report joins the prepared physical session, validated Watch E2E result and
V1 gesture reliability result into one fail-closed, secret-safe artifact.
It intentionally reads only summary/result JSON files; raw transcripts and
assistant responses are never required or copied into the report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class AcceptanceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AcceptanceError(f"cannot read {path.name}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"{path.name} is not valid JSON") from exc
    _require(isinstance(value, dict), f"{path.name} root must be a JSON object")
    return value


def _git_sha(value: Any, *, field: str) -> str:
    _require(isinstance(value, str), f"{field} must be a string")
    normalized = value.strip().lower()
    _require(
        len(normalized) == 40 and all(char in "0123456789abcdef" for char in normalized),
        f"{field} must be a 40-character Git SHA",
    )
    return normalized


def _sha256(value: Any, *, field: str) -> str:
    _require(isinstance(value, str), f"{field} must be a string")
    normalized = value.strip().lower()
    _require(
        len(normalized) == 64 and all(char in "0123456789abcdef" for char in normalized),
        f"{field} must be a 64-character SHA-256",
    )
    return normalized


def build_report(session_dir: Path) -> dict[str, Any]:
    session = _read_json(session_dir / "session.json")
    e2e = _read_json(session_dir / "e2e-result.json")
    v1 = _read_json(session_dir / "v1-result.json")

    _require(session.get("schema_version") == 1, "session schema_version must equal 1")
    app_version = session.get("app_version")
    _require(isinstance(app_version, str) and app_version.strip(), "session app_version must be non-empty")
    app_version = app_version.strip()
    source_revision = _git_sha(session.get("source_revision"), field="session source_revision")
    watch_model = session.get("watch_model")
    _require(isinstance(watch_model, str) and watch_model.strip(), "session watch_model must be non-empty")

    apk_sha = _sha256(session.get("apk_sha256"), field="session apk_sha256")
    installed_apk_sha = _sha256(
        session.get("installed_apk_sha256"),
        field="session installed_apk_sha256",
    )
    _require(apk_sha == installed_apk_sha, "installed APK SHA-256 does not match prepared APK")

    _require(session.get("e2e_passed") is True, "session E2E gate is not marked passed")
    _require(session.get("v1_gate_passed") is True, "session V1 gate is not marked passed")

    _require(e2e.get("valid") is True, "E2E result is not valid")
    _require(e2e.get("outcome") == "success", "E2E outcome must be success")
    _require(e2e.get("route") == "quick_ai", "E2E route must be quick_ai")
    _require(e2e.get("answer_present") is True, "E2E result must prove an answer")
    _require(e2e.get("app_version") == app_version, "E2E app_version does not match session")
    _require(
        _git_sha(e2e.get("source_revision"), field="E2E source_revision") == source_revision,
        "E2E source_revision does not match session",
    )
    latency_ms = e2e.get("latency_ms")
    _require(type(latency_ms) is int and latency_ms >= 0, "E2E latency_ms must be a non-negative integer")

    _require(v1.get("schema_version") == 1, "V1 result schema_version must equal 1")
    _require(v1.get("v1_gate_passed") is True, "V1 result is not passed")
    identity = v1.get("evidence_identity")
    _require(isinstance(identity, dict), "V1 evidence_identity must be an object")
    _require(identity.get("app_version") == app_version, "V1 app_version does not match session")
    _require(
        _git_sha(identity.get("source_revision"), field="V1 source_revision") == source_revision,
        "V1 source_revision does not match session",
    )
    detector_config = identity.get("detector_config")
    _require(
        isinstance(detector_config, str) and detector_config.strip(),
        "V1 detector_config must be non-empty",
    )

    results = v1.get("results")
    requirements = v1.get("requirements")
    _require(isinstance(results, dict), "V1 results must be an object")
    _require(isinstance(requirements, dict), "V1 requirements must be an object")

    raises = results.get("mouth_raise_trials")
    non_triggers = results.get("non_trigger_trials")
    detected = results.get("mouth_raise_detected")
    false_triggers = results.get("false_triggers")
    detection_rate = results.get("detection_rate")
    false_trigger_rate = results.get("false_trigger_rate")
    for field, value in (
        ("mouth_raise_trials", raises),
        ("non_trigger_trials", non_triggers),
        ("mouth_raise_detected", detected),
        ("false_triggers", false_triggers),
    ):
        _require(type(value) is int and value >= 0, f"V1 {field} must be a non-negative integer")
    for field, value in (
        ("detection_rate", detection_rate),
        ("false_trigger_rate", false_trigger_rate),
    ):
        _require(type(value) in (int, float) and 0 <= value <= 1, f"V1 {field} must be between 0 and 1")

    required_raises = requirements.get("mouth_raise_trials")
    required_non_triggers = requirements.get("non_trigger_trials")
    min_detection = requirements.get("min_detection_rate")
    max_false = requirements.get("max_false_trigger_rate")
    _require(type(required_raises) is int and required_raises >= 30, "V1 must require at least 30 raises")
    _require(
        type(required_non_triggers) is int and required_non_triggers >= 100,
        "V1 must require at least 100 non-trigger trials",
    )
    _require(type(min_detection) in (int, float) and min_detection >= 0.90, "V1 detection target is too weak")
    _require(type(max_false) in (int, float) and max_false <= 0.05, "V1 false-trigger target is too weak")
    _require(raises >= required_raises, "V1 result contains too few qualifying raise trials")
    _require(non_triggers >= required_non_triggers, "V1 result contains too few qualifying non-trigger trials")
    _require(detection_rate >= min_detection, "V1 detection rate is below the required target")
    _require(false_trigger_rate <= max_false, "V1 false-trigger rate exceeds the required target")

    return {
        "schema_version": 1,
        "acceptance_passed": True,
        "identity": {
            "app_version": app_version,
            "source_revision": source_revision,
            "watch_model": watch_model.strip(),
            "apk_sha256": apk_sha,
            "detector_config": detector_config.strip(),
        },
        "e2e": {
            "route": "quick_ai",
            "latency_ms": latency_ms,
            "answer_present": True,
            "recorded_at_utc": e2e.get("recorded_at_utc"),
        },
        "v1": {
            "mouth_raise_trials": raises,
            "mouth_raise_detected": detected,
            "detection_rate": detection_rate,
            "non_trigger_trials": non_triggers,
            "false_triggers": false_triggers,
            "false_trigger_rate": false_trigger_rate,
            "rejected_trial_count": v1.get("rejected_trial_count", 0),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    identity = report["identity"]
    e2e = report["e2e"]
    v1 = report["v1"]
    return (
        "# Raise AI physical acceptance report\n\n"
        "**Result: PASS**\n\n"
        f"- App version: `{identity['app_version']}`\n"
        f"- Source revision: `{identity['source_revision']}`\n"
        f"- Watch model: `{identity['watch_model']}`\n"
        f"- APK SHA-256: `{identity['apk_sha256']}`\n"
        f"- Detector config: `{identity['detector_config']}`\n"
        f"- Watch → VPS → provider → Watch: PASS (`quick_ai`, {e2e['latency_ms']} ms)\n"
        f"- Intentional raises: {v1['mouth_raise_detected']}/{v1['mouth_raise_trials']} detected "
        f"({v1['detection_rate'] * 100:.1f}%)\n"
        f"- Non-trigger trials: {v1['false_triggers']}/{v1['non_trigger_trials']} false triggers "
        f"({v1['false_trigger_rate'] * 100:.1f}%)\n"
        f"- Rejected/incomplete trials: {v1['rejected_trial_count']}\n\n"
        "This summary is provenance-bound and intentionally contains no transcript, response text, "
        "gateway token, provider key, or other credential material.\n"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = build_report(args.session_dir)
    except AcceptanceError as exc:
        print(json.dumps({"acceptance_passed": False, "reason": str(exc)}, separators=(",", ":")))
        return 1

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if args.markdown_out:
        args.markdown_out.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
