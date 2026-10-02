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

### Exact-revision deploy attestation

Automated deployments set `RAISE_DEPLOY_REVISION` to the GitHub commit SHA. The gateway exposes that non-secret revision on `GET /health`, and the live smoke test compares it to `github.sha`. This means a green deploy workflow proves the service restarted onto the exact commit that triggered the run instead of merely proving that some gateway process is healthy.

## Live smoke test (VPS)

After a deploy, run on the VPS as the gateway user:

```bash
RAISE_EXPECTED_REVISION=<expected-commit-sha> node gateway/deploy/smoke-live.mjs
```

It reads the token and TLS certificate from `~/.config/raiseai/` (never printed) and
only exercises side-effect-free paths: `/health` with exact revision matching, an
unauthenticated request (must be 401) and an authenticated custom zCloud task, which
the connector must refuse (`zcloud_custom_task_not_supported`). A pass proves the
live gateway is the expected revision and reaches zCloud without starting or pushing
any project. Exit code is non-zero on any failed check.


### Idempotency proof

The deploy workflow deliberately runs the installer a second time with the same revision. `deploy/assert-idempotent-redeploy.sh` verifies, without printing secrets, that the gateway bearer token, TLS public key and deploy revision are unchanged across the repeat deployment. A second exact-revision smoke then proves the restarted service is still healthy and serving the intended commit.


### Dependency-aware smoke policy

A gateway deployment is gated by the live health endpoint, exact revision attestation and authentication behavior. The zCloud connector is probed separately because zCloud may be temporarily unavailable while the Raise gateway itself is correctly deployed. In the default deployment workflow, `zcloud_unavailable` is reported as a degraded dependency and does not roll back or fail the gateway deploy. Set `RAISE_REQUIRE_ZCLOUD=1` when a strict connector-availability gate is desired.

### Machine-readable deployment evidence

Every self-hosted gateway deploy writes `raise-gateway-deploy-evidence.json` and uploads it as the GitHub Actions artifact `raise-gateway-deploy-evidence-<run-id>`. Evidence schema v2 records the workflow run/attempt, commit, observed live revision, systemd active/sub-state, both installed-payload attestations, and the deploy, first-smoke, idempotent-redeploy and repeat-smoke outcomes.

The artifact is intentionally assembled from a fixed allowlist. Gateway bearer tokens, provider API keys, TLS private keys and the full server environment are never serialized. Evidence generation runs under `if: always()`, so failed deployments still leave a machine-readable record when the runner can execute the evidence step.


### Revision-aware restart readiness

The installer no longer assumes that a restarted service is live after a fixed sleep. It now runs `deploy/wait-for-live.mjs`, which polls the TLS `/health` endpoint for up to 30 seconds and only succeeds when the gateway reports `ok: true` **and** the exact expected deploy revision. This makes slower systemd restarts deterministic instead of flaky.

Both the initial deploy and the repeat/idempotency deploy write a secret-safe readiness report. The deploy workflow uploads `raise-ready-initial.json` and `raise-ready-repeat.json` alongside the main deployment evidence artifact. These reports contain only host, expected/live revision, attempt count, elapsed time and the readiness reason; bearer tokens and provider credentials are never serialized.


### Evidence-gated workflow success

The deploy workflow validates its own machine-readable evidence before a run may finish green. `deploy/validate-deploy-evidence.mjs` requires:

- the workflow commit and observed live revision to match the expected GitHub SHA;
- `raise-gateway.service` to be `active/running`;
- deploy, initial smoke, idempotent redeploy and repeat smoke outcomes to be successful;
- both smoke reports to have `ok: true`.

A degraded downstream zCloud dependency is still allowed under the normal dependency-aware smoke policy; the evidence gate is deliberately about proving the gateway deployment itself. The artifact is uploaded before validation, so a failing run retains diagnostic evidence without exposing gateway/provider secrets.


### Installed payload attestation

A green VPS deployment now proves more than the revision string exposed by `/health`. The workflow hashes the exact deploy payload — `gateway/src/**` plus `gateway/package.json` — from the GitHub checkout and compares it with the files actually installed under `~/.local/share/raise-gateway`.

`deploy/attest-payload.mjs` runs after the first install/restart and again after the deliberate idempotent redeploy. Both reports are uploaded with the deployment artifact and folded into deployment evidence schema v2. The evidence gate requires both attestations to succeed and requires the source and installed SHA-256 digests to match.

The payload report contains only aggregate digests, file counts and a reason code. It never serializes file contents, gateway tokens, provider keys, TLS private keys or the gateway environment.
