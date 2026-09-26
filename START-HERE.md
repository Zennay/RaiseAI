# Raise AI v1.0 — START HERE

## Install the new Wear UI

The tested Watch has no Android System WebView service, so v1.0 bundles Mozilla GeckoView. ChatGPT now opens inside Raise AI with a compact round-screen layout, a large prompt, microphone and send button.

## Upgrade from v0.9

1. Double-click **`upgrade-watch.command`**.
2. The first build downloads GeckoView and can take several minutes.
3. Open Raise AI and tap **Open RaiseGPT Wear UI**.
4. Allow microphone access and log in to ChatGPT once.
5. Tap the large website microphone. Review the dictated text and press the green send button.
6. Return to Raise AI and enable raise-to-talk.
7. A fresh raise now reopens RaiseGPT; Gemini remains available from its separate button for Google Home.

See **`CHATGPT-WEB-SETUP.md`** for login, microphone and security details.

## Upgrade from v0.6
Your Watch is already paired. The fastest route is:

1. Unzip this folder.
2. Double-click **`upgrade-watch.command`**.
3. On the Watch confirm:
   - **✓ Hands-free Gemini grant**
   - **✓ Gemini session guard**
   - **✓ Sleep/DND pause**
4. Keep your existing mouth calibration, or recalibrate if needed.
5. Enable raise-to-talk.
6. Test: lower wrist → fresh raise → Gemini opens/listens.
7. While Gemini is still open, another raise must **not** reopen/reset Gemini.

## What changed in v0.7
- Re-arm gate: one trigger stays disarmed until your wrist clearly leaves the mouth pose.
- Gemini session guard: Usage Access checks whether Gemini is still the foreground app.
- 45-second fallback guard if Usage Access is unavailable.
- Sleep/DND pause enabled by default; accelerometer monitoring pauses in quiet mode.
- Lower-power ~10 Hz sensor sampling with batching where supported.
- Runtime stats for active monitoring, sleep pause and blocked retriggers.
- Auto-start attempt after reboot/app update when monitoring was enabled.
- More reliable Watch detection and a self-contained `gradlew` bootstrap.

## Fresh install
Use **`setup-and-install-watch.command`**. It finds the Wear OS device via the watch hardware feature instead of guessing from device order.

## ADB grants used by this personal sideload build
- `SYSTEM_ALERT_WINDOW`: lets a deliberate raise gesture launch Gemini while Raise AI is in the background. Raise AI does not draw overlays.
- `GET_USAGE_STATS`: lets Raise AI see whether Gemini is still foreground so it can suppress retriggers. GitHub, Google account data and Gemini conversation content are not read by this permission.

If the gesture vibrates but Gemini does not open, or Gemini still resets, run `pull-diagnostics.command` and send the output.
