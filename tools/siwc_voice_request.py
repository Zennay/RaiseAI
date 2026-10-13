"""Offline safety contract for a future local SIWC voice client.

No network, login, token storage or Watch transport exists in this module.
The Android companion must reproduce and test these invariants in production.
"""

import re
from typing import Mapping, Sequence


MAX_UTTERANCE_CHARS = 4096
MAX_CONTEXT_MESSAGES = 8
MAX_OUTPUT_CHARS = 12000
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class SiwcContractError(ValueError):
    """The local SIWC request or streamed response violates our contract."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SiwcContractError(f"{label} must be non-empty text")
    if len(value) > MAX_UTTERANCE_CHARS:
        raise SiwcContractError(f"{label} exceeds text limit")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise SiwcContractError(f"{label} contains a control character")
    return value.strip()


def build_text_request(
    transcript: str,
    model: str,
    history: Sequence[Mapping[str, str]] = (),
) -> dict:
    """Build only supported SIWC HTTP Responses fields.

    This is a payload contract, not authorization and not an API transport.
    Callers must first select a model from the authorized account's /v1/models.
    """
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        raise SiwcContractError("model must be an authorized model slug")
    if not isinstance(history, (tuple, list)) or len(history) > MAX_CONTEXT_MESSAGES:
        raise SiwcContractError("history must be a bounded sequence")
    context = []
    for entry in history:
        if not isinstance(entry, dict) or set(entry) != {"role", "content"}:
            raise SiwcContractError("history entry has unexpected fields")
        if entry["role"] not in ("user", "assistant"):
            raise SiwcContractError("only user and assistant history is allowed")
        context.append({"role": entry["role"], "content": _text(entry["content"], "history")})
    context.append({"role": "user", "content": _text(transcript, "transcript")})
    return {
        "model": model,
        "input": context,
        "instructions": (
            "Answer the spoken question clearly and concisely. "
            "Prefer a short answer suitable for a smartwatch; "
            "say when uncertain. Do not claim to remember external ChatGPT chats."
        ),
        "store": False,
        "stream": True,
    }


class ResponseTextAccumulator:
    """Accept model text only after a successful completed Responses stream."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._length = 0
        self._done = False
        self._failed = False

    def feed(self, event: Mapping[str, object]) -> None:
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise SiwcContractError("malformed stream event")
        if self._done or self._failed:
            raise SiwcContractError("stream already terminated")

        event_type = event["type"]
        if event_type in ("response.failed", "response.incomplete", "error"):
            self._failed = True
            raise SiwcContractError("inference did not complete successfully")
        if event_type == "response.completed":
            response = event.get("response")
            if isinstance(response, dict) and response.get("status") != "completed":
                self._failed = True
                raise SiwcContractError("completion event has an invalid status")
            self._done = True
            return
        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            if not isinstance(delta, str):
                raise SiwcContractError("text delta must be a string")
            if self._length + len(delta) > MAX_OUTPUT_CHARS:
                self._failed = True
                raise SiwcContractError("response text exceeds limit")
            self._parts.append(delta)
            self._length += len(delta)

    def finish(self) -> str:
        if self._failed or not self._done:
            raise SiwcContractError("missing successful response.completed")
        answer = "".join(self._parts).strip()
        if not answer:
            raise SiwcContractError("empty completed response")
        return answer
