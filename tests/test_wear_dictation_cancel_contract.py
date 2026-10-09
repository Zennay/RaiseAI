"""Regression contract for cancelling scheduled Wear dictation work.

This deliberately scans the bundled WebExtension source: no Android emulator or
external browser packages are required to validate the cancellation wiring.
"""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app/src/main/assets/raiseai_wear/wear.js"


def test_native_cancel_invalidates_delayed_work():
    source = SOURCE.read_text(encoding="utf-8")
    native_cancel = source.split('message.type === "cancelDictation"', 1)[1].split(
        "\n        }", 1
    )[0]
    assert "interactionEpoch += 1" in native_cancel
    assert "clearSilenceTimer()" in native_cancel
    assert "clearTimeout(startRetryTimer)" in native_cancel
    assert 'state === "finalizing"' in native_cancel


def test_delayed_start_and_send_respect_cancel_epoch():
    source = SOURCE.read_text(encoding="utf-8")
    assert "if (epoch === interactionEpoch) startDictation(source)" in source
    assert 'epoch === interactionEpoch && state === "starting"' in source
    assert 'if (epoch !== interactionEpoch || state !== "finalizing") return;' in source
    assert "clickSendWhenReady(reason, attempt + 1, epoch)" in source
    assert "clickSendWhenReady(reason, 0, epoch)" in source


def test_cancel_discards_unfinished_assistant_reply():
    source = SOURCE.read_text(encoding="utf-8")
    native_cancel = source.split('message.type === "cancelDictation"', 1)[1].split(
        "\n        }", 1
    )[0]
    assert "awaitingAssistantReply = false" in native_cancel
    assert 'assistantCandidate = ""' in native_cancel
    assert "assistantCandidateSince = 0" in native_cancel
    assert "interactionEpoch += 1" in native_cancel


def test_normal_send_still_starts_assistant_wait():
    source = SOURCE.read_text(encoding="utf-8")
    send_path = source.split("function clickSendWhenReady(", 1)[1].split(
        "\n  function finalizeAndSend(", 1
    )[0]
    assert "beginAssistantWait()" in send_path
    assert 'emitState("sending"' in send_path
    assert "send.click()" in send_path
