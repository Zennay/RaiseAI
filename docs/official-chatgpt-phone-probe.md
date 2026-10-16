# Official ChatGPT Android-phone Voice feasibility probe

**Scope:** app-core / [issue #782](https://github.com/Zennay/RaiseAI/issues/782). This is an executable, consent-based feasibility check of the **official consumer ChatGPT Android app**. It is **not** the SIWC/Responses API, not a ChatGPT account emulator, and not proof of a Galaxy Watch audio bridge.

The probe checks the package name, **not the APK's cryptographic signing identity**. Confirm the official publisher/installation through a trusted device app store before testing; a package-name match alone cannot prove authenticity. If the installed app is genuine, it uses its existing signed-in session on the phone. No passwords, cookies, API credentials or transcripts are collected. No undocumented Voice intent, notification action, accessibility automation, web scraping or private endpoint is used.

## Requirements

- A physical, ADB-authorised **Android phone**, with the official ChatGPT Android app installed and signed into the user's account.
- Android platform-tools (`adb`) and Python 3.10+ on the connected workstation.
- No Watch is required for the first **phone-only** launcher/Voice feasibility pass. This experiment does not install any APK.
- A separate on-device test with Watch 7 will be needed before Watch microphone or speaker support can be claimed.

## Run

From the repository root:

```bash
# Safe and read-only: checks exactly one authorised non-Wear Android phone,
# then checks that the claimed `com.openai.chatgpt` package exists (publisher verification must be done separately).
python3 tools/probe_official_chatgpt_phone.py

# If multiple ADB devices are present, bind the intended phone:
python3 tools/probe_official_chatgpt_phone.py --serial <PHONE_SERIAL>

# With user consent: standard Android LAUNCHER category only.
# This *does not* automatically enter Voice or bridge audio.
python3 tools/probe_official_chatgpt_phone.py --launch

# Phone-only observation: press Enter when Voice is listening and when
# its spoken reply is audible. Save private, new-only JSON evidence.
python3 tools/probe_official_chatgpt_phone.py --launch --interactive \
    --evidence ./phone-voice-observation-20261016.json
```

With `--interactive`, manually tap **Voice** inside the official ChatGPT phone app after launch. Press Enter at the two prompts when listening and spoken output are actually observed. Abandon the run (Ctrl-C) if a step fails; **do not fabricate latency or success**.

The measurement labelled `launch_command_ms` is time spent invoking the ADB launcher command; it is **not** visual readiness, trigger-to-listen, inference or Watch end-to-end latency. Operator timing is manually observed and includes reaction delay. The evidence intentionally excludes device serial, transcripts, reply content, ChatGPT account identifiers, screenshots, permission tokens and session data.

### Interpretation

| Check | Meaning |
| --- | --- |
| ADB phone + official package present | The official Android app is installed on one verifiable non-Wear device. |
| Android confirms public MAIN/LAUNCHER start | Public, package-scoped user-facing app start was requested without injecting taps or other UI events; **not** proof of an authentic signature or Voice microphone session. |
| Operator observes Voice listening and spoken reply | A **phone-only**, manually observed interaction; not an automatic Voice deep link. |
| Watch mic reaches official ChatGPT Voice | **UNVERIFIED**, requires lawful supported audio route plus physical Watch/phone test. |
| ChatGPT Voice audible on Watch speaker | **UNVERIFIED**, requires actual paired-device route and physical observation. |

Do not interpret Android Bluetooth call-audio support as normal application audio routing support. Do not substitute SIWC, OpenRouter, VPS Gateway or on-device TTS for this requirement. Do not infer that an ordinary ChatGPT subscription offers a developer API or Watch audio transport.

## Failure handling

The probe refuses offline/unauthorised/multiple unselected devices, Wear devices, absent official app, unexpected ADB results and ambiguous device attributes. It is read-only without `--launch`. The launch option invokes the package's standard Android launcher and never forces Voice open. The JSON evidence file is mode 0600 on POSIX, new-only, symlink-safe and should stay out of Git. Use a fresh filename for each observation. A completed file does **not** certify Voice working from the Watch.

## Regression tests

```bash
python3 -m unittest discover -s tests -p 'test_official_chatgpt_phone_probe.py' -v
```

The 19 Python test scenarios mock ADB and the operator; they check supported launcher-only invocation, fail-closed handling, device selection, no silent app start, strict evidence output, no secret/serial leakage, no symlink overwrite and the missing Watch transport gates. They do **not** provide physical or CI confirmation until the hosted run completes.

**Unchanged hard gate:** [issue #34](https://github.com/Zennay/RaiseAI/issues/34) freezes a specific v1.5.2 Watch acceptance artefact. This tool neither replaces that artefact nor marks the Watch/VPS/model/Watch session verified.
