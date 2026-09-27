# Raise AI Gateway

Minimal native-first routing contract for Raise AI.

Current scope:
- deterministic local routing before any paid model call;
- Bearer-token authentication;
- 16 KiB request-body and 4,000-character transcript limits;
- per-client rate limit;
- no prompt/transcript logging;
- loopback bind by default;
- connector execution deliberately disabled until each connector is configured and tested.

Routes:
- zcloud_task -> long-running project/action work;
- smart_home -> Google Home connector;
- current_info -> freshness/search lane;
- quick_ai -> fast/low-cost LLM lane;
- deep_ai -> deeper LLM lane.

POST /v1/route and POST /v1/assistant expose the routing decision and, for configured AI lanes, the provider result.
They never pretend a downstream connector ran.

Secrets belong in ~/.config/raiseai/gateway.env on the VPS, never in the Watch APK or repository.

## AI provider: OpenRouter + GLM

The AI lane uses OpenRouter and is disabled until OPENROUTER_API_KEY exists on the VPS.

Defaults:
- quick_ai -> z-ai/glm-5.3-flash
- deep_ai -> z-ai/glm-5.3-flash
- fallback -> google/gemini-3.8-flash
- current_info -> same model chain + OpenRouter web search, only when RAISE_ENABLE_WEB_SEARCH=1
- smart_home and zcloud_task never fall through to the LLM provider

Optional overrides:
- RAISE_OPENROUTER_FAST_MODEL
- RAISE_OPENROUTER_DEEP_MODEL
- RAISE_OPENROUTER_FALLBACK_MODELS (comma-separated OpenRouter model IDs)
- RAISE_ENABLE_WEB_SEARCH=1

Example VPS configuration:

```bash
OPENROUTER_API_KEY=...
RAISE_OPENROUTER_FAST_MODEL=z-ai/glm-5.3-flash
RAISE_OPENROUTER_DEEP_MODEL=z-ai/glm-5.3-flash
RAISE_OPENROUTER_FALLBACK_MODELS=google/gemini-3.8-flash
```

OpenRouter receives a prioritized model list. It tries GLM first and can fail over to the configured fallback model without any Watch-app change.

The provider API key belongs in the VPS environment file only. Do not write it to the Watch config, APK, repository, logs, or request payloads.

The legacy direct OpenAI provider module remains in the repository only for compatibility/history; it is no longer imported by the production gateway.

## Persistent TLS deployment

`deploy/install-user-gateway.sh` installs the gateway as a systemd **user** service on port 8787. It requires no root access.

The installer creates a self-hosted TLS certificate for the VPS hostname and derives the SHA-256 pin of its Subject Public Key Info (SPKI). The Watch profile contains:

- `url`: HTTPS gateway URL
- `token`: Raise gateway bearer token
- `spki_sha256`: public-key pin

The Watch still performs normal hostname verification. The optional pin changes certificate trust from public-CA trust to an exact server public-key trust; it does not disable TLS checks.

Provider API keys are deliberately excluded from the Watch profile.

For a future public-CA/reverse-proxy deployment, omit `spki_sha256` and the Watch falls back to Android's normal system trust store.
