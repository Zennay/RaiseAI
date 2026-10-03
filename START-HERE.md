# Raise AI v1.5 — START HERE

Raise AI is native-first:

**raise-to-mouth → native Watch voice UI → secure VPS router → selected connector/provider → Watch**

ChatGPT Web and Gemini are retained as fallbacks; they are no longer the primary raise-to-mouth path.

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
  --require-answer
```

`pull-diagnostics.command` also runs the basic schema/latency gate automatically when Python 3 is available.
11. Treat the physical Watch → VPS gate as proven only when the validator exits 0 for the intended route and the evidence reports a plausible latency.
12. Keep Gemini and ChatGPT Web as UI fallbacks until the native path is stable on the physical Watch.

The Watch evidence file is deliberately content-free: it records route, status, execution flags, latency and input length, but never stores the transcript, response text, gateway token, TLS key material or provider credentials.

## Security boundary

- OpenRouter/provider keys: **VPS only**
- Gateway token: VPS + app-private Watch storage
- TLS private key: **VPS only**
- TLS SPKI pin: public metadata, safe to provision to the Watch
- No provider keys in Git, APK assets, Watch profile, logs, or request payloads

If native routing fails, use the existing Gemini or ChatGPT Web fallback and collect diagnostics before changing the gesture detector.
