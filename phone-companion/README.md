# Raise AI · official ChatGPT Android phone companion (development)

This is a **separate, independent Android-phone application** under `phone-companion/`, not a Wear APK. It can **only** launch the genuine consumer ChatGPT Android app through the public Android launcher after the phone's user explicitly taps a button and supplies a separately trusted official **APK signing certificate SHA-256**.

It **does not** open ChatGPT Voice automatically, inherit account tokens, read ChatGPT chats/memory, capture audio or connect the Galaxy Watch microphone/speaker to ChatGPT. It is **not** Sign in with ChatGPT / Responses API, a private-intent hack or the separately billed VPS gateway. Do not claim success on [issue #782](https://github.com/Zennay/RaiseAI/issues/782) without physical Watch 7 paired-phone audio evidence.

## Features and security boundary

- Dedicated source namespace `nl.zennay.raiseai.phone` but **application ID `nl.zennay.raiseai` intentionally matches the Watch** for future Google Wear Data Layer. Google requires both the same app ID **and APK signing identity** across Watch and phone; transport is not wired yet. A phone build MUST NOT be installed on the Watch.
- Phone manifest contains **no** requested Android permissions; no network, mic, accessibility, background starts or notifications. Only the companion UI is exported.
- The user explicitly pastes a SHA-256 from an **independently authenticated official publisher reference**. Never extract and trust a digest from a potentially compromised phone/APK itself. No fingerprint is shipped, cached, uploaded or generated from a signing key that we control.
- Android `PackageManager.GET_SIGNING_CERTIFICATES` reads the installed `com.openai.chatgpt` signer DER certificate. The app refuses missing, malformed, multiple, nonmatching or unverified signers. It then asks PackageManager for its public MAIN/LAUNCHER component and opens **only** that package.
- Android signing-key rotation may require updating the independently trusted fingerprint; the app fails closed rather than silently accepting an unverified certificate.
- The user must tap Voice **manually inside the official ChatGPT app**. Watch audio transport, streaming and replies have not been implemented. This component never starts apps in the background.

## Build and run on an Android phone

From the root of the RaiseAI repo with a development Android 35 SDK and Gradle dependencies:

```bash
./gradlew -p phone-companion testDebugUnitTest assembleDebug
bash phone-companion/install-phone.command <PHONE_SERIAL>\n# Explicit phone-side replacement/upgrade only after reviewing existing app data:\n# bash phone-companion/install-phone.command <PHONE_SERIAL> --allow-replace
```

The guarded script confirms your explicit ADB serial is an authorized **Android phone**, rejects Wear devices and ambiguous or wrong phone APK identities, and refuses replacing an existing app unless you explicitly pass `--allow-replace`. Because the phone application ID matches the Watch, do **not** run a raw `adb install` against your Watch 7. Do not claim a Data Layer connection unless the phone and Watch builds are actually signed by the same signing key; the self-hosted/debug APK and a separately installed Watch APK may use different keys. Obtain the official ChatGPT signing certificate SHA-256 from a trusted source separate from the installed phone; the project **does not provide an assumed signing reference**. Open Raise AI Phone, enter that fingerprint, and press the explicit verification/launch button. Observe whether the official ChatGPT app opens; Voice activation remains a manual tap and must be separately tested. Never install development APKs onto the frozen physical v1.5.2 Watch acceptance device under [#34](https://github.com/Zennay/RaiseAI/issues/34).

### Required evidence before declaring feature ready

1. Exact-head Android app build + pure JUnit on self-hosted runner.
2. Publisher-authenticated signing fingerprint from independent source, then real-phone signature verification.
3. Real paired Watch 7 ↔ Android phone transport consent, authenticated node identity and actual microphone/speaker routing, with latency evidence. If unsupported, report limitation transparently.

The separate [ADB phone-only feasibility probe](../docs/official-chatgpt-phone-probe.md) can be used to observe the official app without installing this companion.
