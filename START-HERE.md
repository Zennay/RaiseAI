# Raise AI v1.4 — START HERE

Raise AI is now native-first:

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

It does **not** create or copy an OpenAI API key.

## 3. Optional: enable AI provider calls

Provider calls fail closed until a key exists on the VPS.

Add `OPENAI_API_KEY=...` to:

```
~/.config/raiseai/gateway.env
```

Then restart:

```bash
systemctl --user restart raise-gateway
```

Defaults are cost-aware:

- `quick_ai` → `gpt-5.4-nano`
- `deep_ai` → `gpt-5.4-mini`
- `current_info` uses web search only when `RAISE_ENABLE_WEB_SEARCH=1`

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
3. With no provider key, confirm the Watch reports the route as not configured rather than silently falling back or spending money.
4. After adding the provider key, test a simple question; it should use the cheap lane.
5. Test a deliberately complex question; it should use the deeper lane.
6. Only then enable raise-to-talk and test **lower wrist → fresh raise → native listening**.
7. Confirm another raise while listening/sending is blocked.
8. Keep Gemini and ChatGPT Web as fallback until the native path is stable on the physical Watch.

## Security boundary

- OpenAI/provider keys: **VPS only**
- Gateway token: VPS + app-private Watch storage
- TLS private key: **VPS only**
- TLS SPKI pin: public metadata, safe to provision to the Watch
- No provider keys in Git, APK assets, Watch profile, logs, or request payloads

If native routing fails, use the existing Gemini or ChatGPT Web fallback and collect diagnostics before changing the gesture detector.