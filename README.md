# Raise AI v1.5.3 — Galaxy Watch 7

## v1.5.3: bounded microphone retry + Windows installer

- Native voice now allows only one automatic retry after a no-match/speech-timeout error, preventing a stuck microphone retry loop.
- New `install-watch-windows.ps1` downloads the newest successful main APK with GitHub CLI, verifies the ADB target is a Wear OS watch with the expected ABI, installs the APK, launches Raise AI and prints the installed version.
- CI artifact names now follow `VERSION.txt` automatically instead of being hardcoded to v1.5.2.
- v1.5.3 uses versionCode 20.

## v1.5.2: fail-closed build identity

- Evidence-capable Watch builds now require an explicit exact 40-character Git revision and fail if build identity cannot be proven.
- Watch CI verifies that the exact checked-out revision reaches generated BuildConfig before publishing an APK.
- The physical upgrade path runs the same build-identity gate before installation.
- v1.5.2 uses versionCode 19 so the corrected evidence build cannot be confused with the invalid v1.5.1 artifact whose source revision resolved to `unknown`.

## v1.5.1: exact-build physical validation

- `physical-validation.command` turns the real Watch gate into a reproducible **prepare → E2E → 30/100 reliability** session with one evidence directory.
- Physical evidence is now bound to both `app_version` and the exact 40-character Git `source_revision`; a stale APK, dirty source tree, old evidence schema, or mixed detector revision fails closed.
- Native Watch → VPS requests persist a compact `watch-e2e-evidence.json` record with build identity, route, status, latency and execution flags but no transcript, response text or credentials.
- v1.5.1 also fixes release-version drift: `VERSION.txt` and Gradle now agree, and Watch CI enforces that contract.

## v1.5: evidence-gated physical Watch E2E

- Native Watch → VPS requests persist a compact `watch-e2e-evidence.json` record with route, status, latency and execution flags but no transcript, response text or credentials.
- `pull-diagnostics.command` pulls that evidence from app-private storage and runs a strict local validation when Python 3 is available.
- `tools/validate-watch-e2e-evidence.py` fails closed on request failures, unknown routes, schema drift, unexpected fields, stale/future evidence, route/status mismatch or excessive latency. `pull-diagnostics.command` requires evidence from the last 5 minutes by default so an old successful Watch request cannot satisfy a new physical test.
- CI regression-tests the evidence contract and still builds the real Galaxy Watch APK on the self-hosted `vps-bb300bba` runner.
- The version shown on the Watch is read from Gradle build metadata instead of being hardcoded in the activity.

## v1.4: native voice + secure VPS router

- Raise-to-mouth now opens a native Wear OS voice surface instead of putting Gecko/ChatGPT Web on the critical path.
- Dutch speech recognition shows partial transcript text and submits the final utterance to the user's VPS gateway.
- The gateway routes locally before spending API tokens: smart-home commands, zCloud project work, fresh/current information, cheap AI, and deeper AI are separate lanes.
- Optional OpenAI Responses API execution is server-side only: quick AI defaults to `gpt-5.4-nano`, deeper requests to `gpt-5.4-mini`; web search is opt-in.
- Watch → VPS uses HTTPS. A self-hosted certificate can be authenticated with an SPKI SHA-256 pin without disabling hostname verification.
- The gateway token is provisioned into app-private Watch storage; provider API keys remain on the VPS and are never copied to the APK or Watch profile.
- ChatGPT Web and Gemini remain explicit fallback paths while native end-to-end validation continues.
- See `START-HERE.md` and `gateway/README.md` for v1.4 setup.

## v1.3.2: ABI-safe Galaxy Watch build

- The production debug APK is now **armeabi-v7a-only**, matching the ABI reported by the target Galaxy Watch.
- Every `assembleDebug` run automatically verifies the APK and fails unless the native library set is exactly `armeabi-v7a`.
- This prevents x86/x86_64, arm64-only, or stale universal APKs from being handed off again.
- `install-watch-apk.command` auto-finds/reconnects the Watch, caches the last endpoint, compares Watch ABI with APK ABI before install, pins this Mac's Android debug signing key for signature-stable upgrades, and verifies the installed version.
- On macOS, the first successful install also enables `install-mac-adb-autoconnect.command`: a LaunchAgent retries the already-paired Watch every 30 seconds and keeps a backup of the Mac ADB host key. Normal updates should therefore not require re-pairing; pairing is only needed if the Watch itself revokes/forgets the Mac (for example after a factory reset).

## v1.3: spoken replies + 2-second silence + stronger raise detection

- ChatGPT replies are read aloud through the Watch TextToSpeech engine.
- Dictation finalizes after roughly **2 seconds without transcript activity**.
- Fresh raises are blocked while ChatGPT is generating or the Watch is speaking.
- Raise-to-mouth now requires multiple movement samples, an approach from outside the calibrated mouth orientation, and a stable final mouth pose.
- Sensor startup/filter settling no longer counts as intentional arm movement.

## v1.2: fullscreen voice + usable external login

- The microphone is now the primary **fullscreen** Wear OS surface instead of a small panel at the bottom.
- The microphone orb is roughly 2.5× larger and centered for a round Galaxy Watch 7 display.
- Listening, sending and idle states keep the same full-screen layout, with a subtle animated ring and short transcript preview.
- The full-screen surface is hidden whenever the ChatGPT composer is not available. This keeps the real sign-in/account page visible instead of covering it.
- Desktop-assisted login remains the safe external-input route: run `login-from-mac.command`, type on the Mac via scrcpy/ADB, while the actual ChatGPT session and cookies stay on the Watch.
- No ChatGPT password, cookie or session token is copied through a Raise AI server.

## v1.1: voice-first Raise AI

- Raise-to-mouth now opens the existing ChatGPT Wear shell and asks it to start dictation immediately.
- A native ↔ WebExtension state bridge prevents a second gesture from restarting the microphone while the current utterance is still listening/finalizing/sending.
- After the first trigger, the gesture detector must still leave the calibrated mouth pose and re-arm before another trigger can fire.
- The Wear UI is now a centered round-screen voice surface with a large animated microphone orb and a compact live transcript preview.
- Dictation auto-sends after roughly **4 seconds without new transcript text**, giving natural pauses more room than short voice-input timeouts.
- The Gecko engine is prewarmed while monitoring. After ChatGPT has been used, the loaded page is cached for up to 10 minutes instead of keeping a hidden web page alive all day.
- `login-from-mac.command` provides a one-time desktop-assisted login route through ADB/scrcpy. The actual login and cookies remain on the Watch.
- Gemini + Google Home remains available as a separate fallback; Raise AI does not proxy Home credentials or commands through its own backend.

## v1.0: an actual Wear UI

- Bundles Mozilla GeckoView, so Raise AI no longer depends on the missing Android System WebView or Samsung Internet UI.
- Loads the official `chatgpt.com` website in-app and keeps the user's normal web login on the Watch.
- A local built-in WebExtension removes sidebar/desktop clutter and makes the conversation, prompt, microphone and send controls fit a round screen.
- Microphone access is granted only to trusted ChatGPT HTTPS origins; Samsung Internet remains an emergency fallback if GeckoView cannot start.
- Uses no OpenAI API key, private endpoint, copied cookie, backend or per-message API billing.
- Packages only the Galaxy Watch 7 `arm64-v8a` browser binary. The APK is still much larger than v0.9 because it contains a complete browser engine.

## v0.7 daily-driver optimizations retained

- **No Gemini reset loop:** trigger is disarmed until the wrist leaves the mouth pose; Usage Access additionally blocks launches while Gemini is foreground.
- **Sleep/DND pause:** monitoring pauses when the Watch is in Do Not Disturb/Bedtime quiet mode.
- **Lower-power sampling:** ~10 Hz accelerometer sampling plus FIFO batching where supported.
- **Runtime counters:** active minutes, sleep-paused minutes and blocked Gemini retriggers.
- **Auto-start:** attempts to restart monitoring after reboot/app update if it was enabled.
- **Installer fixes:** Wear-feature based watch detection, direct APK install, SDK path setup and a self-contained Gradle bootstrap.

Raise AI is a personal Wear OS **raise-to-mouth → native voice → VPS router** assistant for Samsung Galaxy Watch 7. The VPS decides whether a request should use a low-cost AI model, a stronger model, current-information search, Google Home, or a zCloud worker.

Provider secrets live only on the VPS. The Watch receives only the Raise gateway URL, a dedicated gateway token, and—when self-hosted TLS is used—the public-key pin. ChatGPT Web and Gemini remain available as fallbacks.

**Start with `START-HERE.md`.** Gateway details live in `gateway/README.md`; legacy ChatGPT Web fallback setup remains in `CHATGPT-WEB-SETUP.md` / `REMOTE-LOGIN.md`; Gemini + Google Home fallback details remain in `GEMINI-HOME-SETUP.md`.

## What v0.9 fixed

- Detects that the tested Galaxy Watch 7 has Samsung Internet but no Android System WebView service.
- Opens ChatGPT in `com.sec.android.app.sbrowser` instead of crashing the embedded activity.
- Keeps embedded ChatGPT Web available on Wear OS devices that do expose a WebView provider.
- Blocks gesture retriggers while Samsung Internet is foreground.
- Corrects the installer output to v0.9 / ChatGPT instead of the stale v0.7 / Gemini text.

## What v0.8 added

- A Wear OS WebView that loads the official `chatgpt.com` site and keeps its cookie session locally.
- Android and WebView microphone permission handling restricted to trusted ChatGPT HTTPS origins.
- An automatic attempt to click ChatGPT's own dictation button after a raise.
- No API key, token billing, response scraping or private ChatGPT endpoints.
- ChatGPT as the default raise-to-mouth target, while Gemini and Google Home remain separate fallbacks.
- A session guard that also prevents ChatGPT from being reopened while Raise AI is foreground.

## What V0.3 does

- Calibrates the physical orientation of **your** watch when held near your mouth.
- Runs an opt-in foreground sensor service using the accelerometer.
- Requires recent movement + calibrated mouth orientation + a short hold before triggering.
- Gives a short haptic when a raise is detected.
- Attempts Android `VOICE_COMMAND` first for an immediate voice session, then falls back to `ACTION_ASSIST`.
- Includes separate **Test Gemini voice / Test AI question / Test Google Home command** buttons so assistant/account integration can be tested separately from the gesture.
- Counts real gesture triggers so detection can be separated from Gemini-launch problems.
- Records labeled Watch 7 sensor traces for **mouth raise / check time / normal movement**.
- Includes a one-command ADB export of those traces.
- Gives the monitoring notification a **Gemini** fallback if Android blocks hands-free background launch.

## Important V0.3 limitation

Modern Android restricts background activity launches. The gesture detector itself is implemented, but whether the background trigger can open Gemini hands-free must be verified on the real Watch 7 / current One UI Watch build. The app intentionally keeps a foreground notification visible while monitoring.

If a raise increases the **Triggers** counter but Gemini does not appear, the gesture worked and the remaining problem is specifically the assistant/background bridge.

## Easiest install

### Android Studio

1. Install a current Android Studio.
2. Double-click `open-in-android-studio.command`, or open this folder manually.
3. Let Gradle sync; install Android SDK Platform 35 / API 35 if prompted.
4. On Watch 7 enable **Developer options → Wireless debugging**.
5. Android Studio → **Pair Devices Using Wi-Fi** → select the Watch 7 → **Run**.
6. Watch: **Calibrate mouth pose → Test Gemini voice → Test Google Home command → Enable raise-to-talk**.

### macOS script

After Android Studio is installed:

```bash
./setup-and-install-watch.command
```

The script uses Android Studio's bundled Java when possible, detects the usual macOS Android SDK location, creates `local.properties`, creates a Gradle 9.6 wrapper if needed, pairs ADB, builds, installs and launches the app.

## Collect gesture evidence

In the watch app, record several examples of each:

1. **Record mouth raise · 4 sec**
2. **Record check-time raise · 4 sec**
3. **Record normal movement · 4 sec**

Then run:

```bash
./pull-watch-data.command
```

It pulls `sensor-traces.csv` from the debug build into this folder. The CSV contains label, session id, elapsed milliseconds and x/y/z accelerometer values.

Then run the canonical trace validator:

```bash
python3 tools/analyze-watch-sensor-traces.py sensor-traces.csv
```

It validates the exported CSV fail-closed, groups samples into capture sessions, rejects malformed/non-finite evidence, and reports progress toward the V1 dataset gate of 30 qualifying mouth raises plus 100 qualifying non-trigger sessions. Add `--require-v1-gate` when you want the command to exit non-zero until that evidence gate is complete.

## Project structure

```text
app/src/main/java/nl/zennay/raiseai/
├── MainActivity.kt              # setup, calibration, ChatGPT/Gemini tests, trace recording
├── ChatGptActivity.kt           # bundled GeckoView shell + trusted microphone bridge
├── assets/raiseai_wear/         # Wear CSS/JS built-in WebExtension
├── ChatGptLauncher.kt           # foreground/background ChatGPT activity launch
├── GestureMonitorService.kt     # opt-in foreground sensor monitor
├── RaiseGestureDetector.kt      # small testable detector
├── SensorTraceRecorder.kt       # labeled Watch 7 CSV traces
├── CalibrationStore.kt          # mouth-pose, enabled state, trigger stats
├── AssistantLauncher.kt         # Android voice-command / assist bridge
├── AssistantProxyActivity.kt    # experimental background bridge
└── HomeLauncher.kt              # Google Home app fallback / setup helper
```

## Build tooling

- Android Gradle Plugin 9.4.0
- Gradle 9.6.0
- compile / target SDK 35
- Java 17 bytecode target
- AGP 9 built-in Kotlin (no legacy `org.jetbrains.kotlin.android` plugin)
- Mozilla GeckoView 139, Galaxy Watch `armeabi-v7a` build

## Gemini + Google Home

Raise AI uses your real Gemini assistant. If Google Home is enabled under Gemini Connected apps on the paired phone, supported smart-home commands are handled by Gemini itself — Raise AI does not need a separate Home API or cloud backend. See `GEMINI-HOME-SETUP.md`.

## Diagnostics

Run `pull-diagnostics.command` after a test session to export Raise AI logcat, package/service state, battery information and sensor traces into one folder.

## Next proof gate

The current product gate is the **frozen v1.5.2 physical acceptance session** from merged-main revision `8f719bb273f9b997848864f342598e7df5f090e5`, carried by GitHub Release tag `physical-handoff-v1.5.2-8f719bb`, Release asset id `611084738`, with archive digest `sha256:867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce`. Any different carrier or rebuilt APK is not acceptance evidence.

Do not use the older Gemini-first checklist as the acceptance path. Follow [PHYSICAL-ACCEPTANCE.md](PHYSICAL-ACCEPTANCE.md) to verify the exact published handoff, install/provision it on the Galaxy Watch 7, prove one Watch → VPS → provider → Watch `quick_ai` round trip, and collect the provenance-bound 30 intentional / 100 non-trigger V1 reliability set.

`DEVICE-TEST.md` is retained as historical V0.3 Gemini-fallback context only.

## v0.6: hands-free Gemini fix
- Removed generic `ACTION_VOICE_COMMAND` because Samsung routed it to Bixby.
- Uses the physically verified `ACTION_ASSIST` scoped to `com.google.android.wearable.assistant`.
- Installer grants the personal-sideload `SYSTEM_ALERT_WINDOW` app-op over ADB so a raise gesture can launch Gemini while Raise AI is in the background.
- Automatically prefers a connected Wear OS watch over a connected Android phone.
- Added `upgrade-watch.command` for one-click updates once the Watch is already paired.