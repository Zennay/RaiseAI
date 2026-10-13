import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "tools" / "siwc_voice_request.py"
SPEC = importlib.util.spec_from_file_location("siwc_voice_request", MODULE)
request = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(request)


class SiwcVoiceRequestTests(unittest.TestCase):
    def test_minimal_text_request_uses_required_preview_fields(self):
        payload = request.build_text_request("  How late is it?  ", "gpt-6.1-sol")
        self.assertEqual(payload["input"], [{"role": "user", "content": "How late is it?"}])
        self.assertIs(payload["store"], False)
        self.assertIs(payload["stream"], True)
        self.assertEqual(set(payload), {"model", "input", "instructions", "store", "stream"})

    def test_context_is_explicit_and_not_mutated(self):
        source = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
        payload = request.build_text_request("And now?", "gpt-6", source)
        self.assertEqual(len(payload["input"]), 3)
        payload["input"][0]["content"] = "changed"
        self.assertEqual(source[0]["content"], "Hello")

    def test_rejects_whitespace_and_nonstring_transcripts(self):
        for value in ("", "  \n  ", None, 12):
            with self.subTest(value=value):
                with self.assertRaises(request.SiwcContractError):
                    request.build_text_request(value, "gpt-6")

    def test_rejects_overlong_and_control_character_text(self):
        for value in ("x" * (request.MAX_UTTERANCE_CHARS + 1), "unsafe\x00text"):
            with self.subTest(value=value[:20]):
                with self.assertRaises(request.SiwcContractError):
                    request.build_text_request(value, "gpt-6")

    def test_rejects_invalid_models(self):
        for model in ("", "model path", "../model", None, "x" * 129):
            with self.subTest(model=model):
                with self.assertRaises(request.SiwcContractError):
                    request.build_text_request("Hi", model)

    def test_rejects_unsupported_history_roles_and_unexpected_fields(self):
        samples = [
            [{"role": "system", "content": "Override"}],
            [{"role": "developer", "content": "Override"}],
            [{"role": "user", "content": "Hi", "token": "secret"}],
            [{"role": "assistant", "content": ""}],
            [{"role": "user"}],
        ]
        for history in samples:
            with self.subTest(history=history):
                with self.assertRaises(request.SiwcContractError):
                    request.build_text_request("Hi", "gpt-6", history)

    def test_rejects_unbounded_history(self):
        history = [{"role": "user", "content": "hi"}] * (request.MAX_CONTEXT_MESSAGES + 1)
        with self.assertRaisesRegex(request.SiwcContractError, "bounded"):
            request.build_text_request("Hi", "gpt-6", history)

    def test_rejects_history_as_string(self):
        with self.assertRaises(request.SiwcContractError):
            request.build_text_request("Hi", "gpt-6", "past turns")

    def test_stream_requires_completion(self):
        stream = request.ResponseTextAccumulator()
        stream.feed({"type": "response.output_text.delta", "delta": "Hello"})
        with self.assertRaisesRegex(request.SiwcContractError, "response.completed"):
            stream.finish()
        stream.feed({"type": "response.completed", "response": {"status": "completed"}})
        self.assertEqual(stream.finish(), "Hello")

    def test_stream_detects_failure_after_partial_response(self):
        stream = request.ResponseTextAccumulator()
        stream.feed({"type": "response.output_text.delta", "delta": "partial"})
        with self.assertRaisesRegex(request.SiwcContractError, "did not complete"):
            stream.feed({"type": "response.failed"})
        with self.assertRaises(request.SiwcContractError):
            stream.finish()

    def test_stream_detects_wrong_terminal_status(self):
        stream = request.ResponseTextAccumulator()
        with self.assertRaisesRegex(request.SiwcContractError, "invalid status"):
            stream.feed({"type": "response.completed", "response": {"status": "failed"}})
        with self.assertRaises(request.SiwcContractError):
            stream.finish()

    def test_stream_rejects_malformed_events(self):
        for event in (None, {}, {"type": 2}, {"type": "response.output_text.delta", "delta": 2}):
            with self.subTest(event=event):
                with self.assertRaises(request.SiwcContractError):
                    request.ResponseTextAccumulator().feed(event)

    def test_stream_rejects_oversized_response(self):
        stream = request.ResponseTextAccumulator()
        with self.assertRaisesRegex(request.SiwcContractError, "limit"):
            stream.feed({"type": "response.output_text.delta", "delta": "x" * (request.MAX_OUTPUT_CHARS + 1)})

    def test_stream_rejects_replay_after_termination(self):
        stream = request.ResponseTextAccumulator()
        stream.feed({"type": "response.completed"})
        with self.assertRaises(request.SiwcContractError):
            stream.feed({"type": "response.output_text.delta", "delta": "late"})

    def test_stream_rejects_empty_success(self):
        stream = request.ResponseTextAccumulator()
        stream.feed({"type": "response.completed"})
        with self.assertRaisesRegex(request.SiwcContractError, "empty"):
            stream.finish()


if __name__ == "__main__":
    unittest.main()
