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
- quick_ai -> fast/low-cost LLM lane.

POST /v1/route and POST /v1/assistant currently expose the routing decision.
They do not pretend a downstream connector ran.

Secrets belong in /etc/raise-gateway.env, never in the Watch APK or repository.

## Cost-aware AI provider

The OpenAI lane is optional and disabled until OPENAI_API_KEY exists on the VPS.

Defaults:
- quick_ai -> gpt-5.4-nano
- deep_ai -> gpt-5.4-mini
- current_info -> gpt-5.4-nano + web_search, but only when RAISE_ENABLE_WEB_SEARCH=1
- smart_home and zcloud_task never fall through to the LLM provider

Optional overrides:
- RAISE_OPENAI_FAST_MODEL
- RAISE_OPENAI_DEEP_MODEL
- RAISE_ENABLE_WEB_SEARCH=1

The API key belongs in the VPS environment file only. Do not write it to the Watch config, APK, repository, logs, or request payloads.