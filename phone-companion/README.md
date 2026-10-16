# Raise AI · official ChatGPT Android phone companion (development)

This is a **separate, independent Android-phone application** under `phone-companion/`, not a Wear APK. It can **only** launch the genuine consumer ChatGPT Android app through the public Android launcher after the phone's user explicitly taps a button and supplies a separately trusted official **APK signing certificate SHA-256**.

It **does not** open ChatGPT Voice automatically, inherit account tokens, read ChatGPT chats/memory, capture audio or connect the Galaxy Watch microphone/speaker to ChatGPT. It is **not** Sign in with ChatGPT / Responses API, a private-intent hack or the separately billed VPS gateway. Do not claim success on [issue #782](https://github.com/Zennay/RaiseAI/issues/782) without physical Watch 7 paired-phone audio evidence.

## Features and security boundary

- Dedicated package `nl.zennay.raiseai.phone` — never installed over the Watch app `nl.zennay.raiseai`.
- Phone manifest contains **no** requested Android permissions; no network, mic, accessibility, background starts or notifications. Only the companion UI is exported.
- The user explicitly pastes a SHA-256 from an **independently authenticated official publisher reference**. Never extract and trust a digest from a potentially compromised phone/APK itself. No fingerprint is shipped, cached, uploaded or generated from a signing key that we control.
- Android `PackageManager.GET_SIGNING_CERTIFICATES` reads the installed `com.openai.chatgpt` signer DER certificate. The app refuses missing, malformed, multiple, nonmatching or unverified signers. It then asks PackageManager for its public MAIN/LAUNCHER component and opens **only** that package.
- Android signing-key rotation may require updating the independently trusted fingerprint; the app fails closed rather than silently accepting an unverified certificate.
- The user must tap Voice **manually inside the official ChatGPT app**. Watch audio transport, streaming and replies have not been implemented. This component never starts apps in the background.

## Build and run on an Android phone

From the root of the RaiseAI repo with a development Android 35 SDK and Gradle dependencies:

```bash
./gradlew -p phone-companion testDebugUnitTest assembleDebug
adb -s <PHONE_SERIAL> install -r phone-companion/build/outputs/apk/debug/phone-companion-debug.apk
```

Confirm the target is a genuine **Android phone**, not the Galaxy Watch 7, before installing. Obtain the official ChatGPT signing certificate SHA-256 from a trusted source separate from the installed phone; the project **does not provide an assumed signing reference**. Open Raise AI Phone, enter that fingerprint, and press the explicit verification/launch button. Observe whether the official ChatGPT app opens; Voice activation remains a manual tap and must be separately tested. Never install development APKs onto the frozen physical v1.5.2 Watch acceptance device under [#34](https://github.com/Zennay/RaiseAI/issues/34).

### Required evidence before declaring feature ready

1. Exact-head Android app build + pure JUnit on self-hosted runner.
2. Publisher-authenticated signing fingerprint from independent source, then real-phone signature verification.
3. Real paired Watch 7 ↔ Android phone transport consent, authenticated node identity and actual microphone/speaker routing, with latency evidence. If unsupported, report limitation transparently.

The separate [ADB phone-only feasibility probe](../docs/official-chatgpt-phone-probe.md) can be used to observe the official app without installing this companion.
