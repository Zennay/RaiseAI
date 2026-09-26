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
