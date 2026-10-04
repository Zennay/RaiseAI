# Raise AI v1.5.2 — START HERE

Raise AI is native-first:

**raise-to-mouth → native Watch voice UI → secure VPS router → selected connector/provider → Watch**

ChatGPT Web and Gemini are retained as fallbacks; they are no longer the primary raise-to-mouth path.

## Preferred physical validation flow

For the current M0/V0 gate, use the session orchestrator on the Mac paired with the Galaxy Watch 7:

```bash
bash ./physical-validation.command all /path/to/watch-gateway.properties
```

The flow is fail-closed and keeps one evidence directory under `~/.raiseai/evidence/`:

1. **prepare** requires a clean Git checkout, binds the APK to the exact 40-character source revision, builds/installs v1.5.2, provisions the gateway profile, clears only old validation evidence, and opens Raise AI;
2. **verify-e2e** accepts only a fresh `quick_ai` response from the exact prepared app version and Git revision;
3. **verify-v1** is allowed only after E2E passes and requires the full 30 intentional raises / 100 non-trigger dataset with ≥90% detection and ≤5% false triggers.

The manual commands remain available when debugging an individual stage:

```bash
bash ./physical-validation.command prepare /path/to/watch-gateway.properties
bash ./physical-validation.command verify-e2e
bash ./physical-validation.command verify-v1
bash ./physical-validation.command status
```

A dirty source tree cannot produce passing physical evidence. Old v1 schema evidence also fails closed; v1.5.2 writes schema v2 with `app_version` and `source_revision`.

## 1. Install or upgrade the Watch app

On the Mac already paired with the Galaxy Watch 7:

1. Run `upgrade-watch.command` (or `setup-and-install-watch.command` for a fresh install).
2. The build must pass the Watch ABI check for `armeabi-v7a`.
3. Open Raise AI once and allow microphone/notification permissions.
4. Keep the existing mouth calibration or recalibrate if needed.
5. Do not remove ChatGPT/Gemini fallback setup yet.

## 2. Install the VPS gateway

On the VPS, from the RaiseAI repository:

```bash
bash gateway/deploy/install-user-gateway.sh
```

The installer is user-level: it does not require root. It creates:

- a persistent systemd user service;
- a random Raise gateway token;
- a private TLS key and self-hosted certificate;
- an SPKI SHA-256 public-key pin;
- `~/.config/raiseai/watch-gateway.properties` for Watch provisioning.

It does **not** create or copy an OpenRouter API key.

## 3. Enable GLM through OpenRouter

Provider calls fail closed until an OpenRouter key exists on the VPS.

Add this to:

```
~/.config/raiseai/gateway.env
```

```bash
OPENROUTER_API_KEY=sk-or-v1-...
RAISE_OPENROUTER_FAST_MODEL=z-ai/glm-5.3-flash
RAISE_OPENROUTER_DEEP_MODEL=z-ai/glm-5.3-flash
RAISE_OPENROUTER_FALLBACK_MODELS=google/gemini-3.8-flash
```

Then restart:

```bash
systemctl --user restart raise-gateway
```

Defaults are cost-aware and Watch-first:

- `quick_ai` → `z-ai/glm-5.3-flash`
- `deep_ai` → `z-ai/glm-5.3-flash`
- automatic model fallback → `google/gemini-3.8-flash`
- `current_info` uses OpenRouter web search only when `RAISE_ENABLE_WEB_SEARCH=1`
- `smart_home` and `zcloud_task` do not call an LLM

The Watch does not know or store the OpenRouter key or provider model IDs.

Google Home and zCloud execution remain disabled until their own connectors are validated.

## 4. Provision the Watch gateway profile

Copy `watch-gateway.properties` from the VPS to the paired Mac using your normal secure SSH/SCP route.

Then run:

```bash
bash provision-watch-gateway.command /path/to/watch-gateway.properties
```

The helper validates HTTPS, the gateway token length and the TLS public-key pin, finds the Wear OS device, and copies the profile into Raise AI's app-private storage. It does not print the token.

The debug APK must already be installed because provisioning uses Android `run-as`.

## 5. Test in this order

1. Open **Native Raise AI** manually.
2. Speak a short request and confirm the transcript appears.
3. With no provider key, confirm the Watch reports `openrouter_not_configured` rather than silently falling back or spending money.
4. Add the OpenRouter key and ask a simple question; the response should report GLM 5.3 Flash as the serving model unless OpenRouter had to fail over.
5. Test a deliberately complex question and confirm the `deep_ai` lane still uses the configured GLM model chain.
6. Enable `RAISE_ENABLE_WEB_SEARCH=1` only if current-info queries should be allowed to incur search cost, then test a fresh-information question.
7. Only then enable raise-to-talk and test **lower wrist → fresh raise → native listening**.
8. Confirm another raise while listening/sending is blocked.
9. Run `./pull-diagnostics.command` immediately after the physical test. When at least one native gateway request has completed, the bundle includes `watch-e2e-evidence.json`.
10. Validate the evidence explicitly. For a normal AI-answer smoke test:

```bash
python3 tools/validate-watch-e2e-evidence.py \
  watch-diagnostics-*/watch-e2e-evidence.json \
  --expect-route quick_ai \
  --max-latency-ms 15000 \
  --max-age-seconds 300 \
  --require-answer \
  --expect-app-version 1.5.2 \
  --expect-source-revision <40-character-git-sha>
```

`pull-diagnostics.command` also runs the basic schema/latency/freshness gate automatically when Python 3 is available. By default it rejects evidence older than 300 seconds; override only for deliberate diagnostics with `RAISE_E2E_MAX_AGE_SECONDS`.
11. Treat the physical Watch → VPS gate as proven only when the validator exits 0 for the intended route and the evidence reports a plausible latency.
12. Keep Gemini and ChatGPT Web as UI fallbacks until the native path is stable on the physical Watch.

The Watch evidence file is deliberately content-free: it records app version, exact source revision, route, status, execution flags, latency and input length, but never stores the transcript, response text, gateway token, TLS key material or provider credentials.

## 6. Run the V1 gesture reliability evidence session

The three **Record** buttons now run a 4-second detector trial without launching the assistant. The app temporarily suppresses the live gesture service during the trial, samples at the same ~10 Hz request used by the service, and records whether the same `RaiseGestureDetector` triggered.

Collect at least:

- 30 `mouth_raise` trials;
- 100 non-trigger trials across `view_time` and `normal_move`.

Then export and score them:

```bash
./pull-watch-data.command
```

The export includes raw `sensor-traces.csv` plus `sensor-trials.csv` with per-trial detector outcomes. To make the command fail unless the roadmap gate is actually met:

```bash
RAISE_REQUIRE_V1_TRIAL_GATE=1 ./pull-watch-data.command
```

The V1 gate passes only when there are at least 30 qualifying mouth raises and 100 qualifying non-trigger trials, intentional-raise detection is at least 90%, and false-trigger rate is at most 5%. Short/incomplete trials are excluded from the denominator.

## Security boundary

- OpenRouter/provider keys: **VPS only**
- Gateway token: VPS + app-private Watch storage
- TLS private key: **VPS only**
- TLS SPKI pin: public metadata, safe to provision to the Watch
- No provider keys in Git, APK assets, Watch profile, logs, or request payloads

If native routing fails, use the existing Gemini or ChatGPT Web fallback and collect diagnostics before changing the gesture detector.
