# Raise AI: ChatGPT account-powered voice mode (feasibility + safe implementation contract)

**Status: additive prototype only. Not a working Watch integration or physical-device proof.**  
**Tracking:** https://github.com/Zennay/RaiseAI/issues/782  
**Hardware gate still controls V1:** https://github.com/Zennay/RaiseAI/issues/34

## Product

Raise-to-mouth or tap -> native Wear speech recognition -> AI request -> short spoken answer on the Watch. No browser in the critical interaction path. A clean full-screen listening orb, short transcript, streaming response text, and a cancel button; longer answers only on request. Native TTS provides the voice, not a ChatGPT Voice session.

Keep the existing Raise gateway as a **distinct, explicitly chosen** alternative. It is not part of the ChatGPT-plan account route and may carry separate provider billing.

## Why an Android phone companion

OpenAI's official **Sign in with ChatGPT** (SIWC) open-source integration lets eligible users authorize an OSS client to use ChatGPT-plan-backed Responses API requests. The documented public-client flow uses browser/OIDC/PKCE, dynamic client registration, a stable \`ext_agent_host_id\`, and a \`127.0.0.1\` callback. For this product, the paired Android phone is the proposed **user-controlled OAuth host**: it has a normal browser and secure local credential storage. Do not assume a callback flow tested on desktop automatically works on Android; prove it on the actual phone.

The Wear app sends only a bounded transcript and request identifier over Wear OS Data Layer. The Android phone obtains user consent, owns the local OAuth session and makes inference calls. Only text deltas, terminal status, and safe error labels return to the Watch. Do not put tokens, browser cookies, refresh tokens, raw transcript logs, or identity claims in the VPS, APK, project telemetry, GitHub Actions, or watch-to-phone messages.

## Explicit limitations (October 2026)

- ChatGPT identity alone is not permission to spend plan usage; separate Responses scopes and user consent are required.
- SIWC open-source preview supports the **Responses API**, with \`store: false\`, \`stream: true\`, \`input\` as an array and explicit relevant conversational context per turn.
- Audio/video input and OpenAI transcription API are **not supported** in this sign-in flow. Perform speech recognition and TTS with Android/Wear facilities.
- No access to normal ChatGPT memories, chat history, uploaded files or Voice experience.
- Do not use \`chatgpt.com/backend-api\`, copy cookies or use the ChatGPT website as an inference API.
- Do not send unsupported Responses fields (\`temperature\`, \`max_output_tokens\`, \`previous_response_id\`, \`conversation\`, \`metadata\`, etc.).
- Account-owned limits apply and can be exhausted. Present an honest out-of-usage state. Never silently switch to a billed provider.
- Local user-controlled storage is a condition of SIWC use. Never use a centrally managed token relay.
- No real latency, battery, wake-word or physical Watch quality claims without physical testing.

## Proposed architecture

\`\`\`text
Galaxy Watch 7 (Raise AI native Wear app)
  -> trusted user gesture or tap
  -> Watch SpeechRecognizer / transcript
  -> authenticated/bound Wear OS Data Layer request {id, transcript, mode}
  -> paired Android companion
       -> local system-browser SIWC OIDC authorization with PKCE / loopback
       -> local Android Keystore-backed credential storage
       -> account-scoped /v1/models discovery (user-selectable model)
       -> POST https://api.openai.com/v1/responses (store=false, stream=true)
       -> validate SSE deltas and require response.completed
  <- bounded text chunks or safe terminal error (no credentials)
  -> native Watch TTS, short by default, cancel/retry controls
\`\`\`

**App core owner safety:** no changes in this proof to \`NativeVoiceActivity\`, gesture service, TLS/gateway clients, login Gecko wrapper, CI, physical acceptance artifact or the active PRs that own those files.

## First committed proof

\`tools/siwc_voice_request.py\` and \`tests/test_siwc_voice_request.py\` implement and test a **network-free text request and response-stream contract**. This is only a portable fixture/reference for the future phone-client implementation. It does not perform OAuth, access an account, contact OpenAI, install on a Watch, or dispatch to an Android phone. The companion must implement equivalent validation in its production language and own integration tests.

Run focused proof locally:

\`\`\`bash
python3 -m unittest tests.test_siwc_voice_request -v
\`\`\`

## Acceptance stages

1. Android phone: system browser registration/sign-in, validated state + nonce + issuer + audience + PKCE, stable host identity, local at-rest protection, robust token refresh/account switch/sign-out, physical confirmation.
2. Phone: list models using authorized access token; build only allowed request shape; streaming SSE completion/error proof; local bounded history; no accidental transcript/credential logs.
3. Watch transport: verified pairing/source, bounded payloads, replay protection, streaming backpressure, timeout/cancel; no token on Watch or VPS.
4. UX: gesture/mic permission, visible listening -> thinking -> speaking, concise answer, optional detailed answer, offline and quota states.
5. Physical Watch 7 acceptance: measure wake latency, on-device speech recognition quality (NL/EN), answer latency, battery, false triggers and failures. Respect frozen V1 issue #34 before claiming daily-driver readiness.

## Sources

- https://developers.openai.com/siwc/token-sharing-open-source
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
- https://openai.com/policies/sign-in-with-chatgpt-terms/
