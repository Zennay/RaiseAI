# Hands-free gesture setup (development builds)

Raise AI defaults to **Gemini** on a fresh install. On the Watch, choose **Native Raise AI** only if you want its own VPS-backed voice flow. The gesture detector uses the accelerometer: it does not need a motion-sensor runtime permission.

## On the Watch

1. Open **Raise AI** and tap **Calibrate mouth pose**. Hold the watch near your mouth during calibration.
2. Under **Hands-free setup**, tap **Allow background AI launch**. Only grant access in Android settings if that screen is actually available. Return to Raise AI and verify **✓ Background AI launch allowed**.
3. If Wear OS does not expose the background-launch grant in settings, use the existing trusted `install-watch-apk.command` flow, which applies the special app-op with ADB. For an already installed app on your *own* paired watch, after explicitly selecting the intended device:
   ```bash
   adb -s <YOUR_WATCH_SERIAL> shell appops set nl.zennay.raiseai SYSTEM_ALERT_WINDOW allow
   adb -s <YOUR_WATCH_SERIAL> shell appops get nl.zennay.raiseai SYSTEM_ALERT_WINDOW
   ```
   Reopen the app and confirm the on-screen grant status; granting the app-op is not proof that Wear OS will permit every background activity launch.
4. **Enable usage access (optional)** improves prevention of duplicate assistant opens; without it the app uses a conservative 30-second guard. On devices without a Wear settings UI the installer can apply the corresponding app-op.
5. **Allow microphone (Native AI)** requests Android `RECORD_AUDIO` at runtime. Gemini handles microphone access in the Google assistant app, so Raise AI's mic grant is not a prerequisite for Gemini.
6. Tap **Enable raise-to-talk**. With no calibration or background launch grant, the app refuses to claim monitoring has started. A foreground notification indicates active monitoring when it starts.
7. Tap **Test raise gesture · 4 sec**, then raise your wrist toward your mouth. The test records the detector result **without launching AI**; it restores monitoring afterwards. The existing **Open main AI** and **Test Gemini voice** buttons exercise assistant launch separately.

## Real hardware validation required

For the selected Watch, test first with Raise AI visible, then from the watch face, then with the screen asleep. Verify a vibration, an incremented trigger count and **Gemini opening and listening**. If a vibration and counter increment occur but no assistant opens, inspect the **Assistant route** status and `pull-diagnostics.command`; foreground activity-start restrictions may still apply.

The foreground-service start acknowledgement is not proof of on-device recognition or successful background launch. Do not mark gesture-to-Gemini or mic-start as physically verified without the actual Watch result.

**Important:** these changes are for later development builds. Do not modify, replace or claim success for the separately frozen **v1.5.2 physical acceptance artifact** tracked in issue #34.
