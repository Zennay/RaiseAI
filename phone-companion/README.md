# Raise AI · official ChatGPT Android phone companion (development)

This is a **separate, independent Android-phone application** under `phone-companion/`, not a Wear APK. It can **only** launch the genuine consumer ChatGPT Android app through the public Android launcher after the phone's user explicitly taps a button and supplies a separately trusted official **APK signing certificate SHA-256**.

It **does not** open ChatGPT Voice automatically, inherit account tokens, read ChatGPT chats/memory, capture audio or connect the Galaxy Watch microphone/speaker to ChatGPT. It is **not** Sign in with ChatGPT / Responses API, a private-intent hack or the separately billed VPS gateway. Do not claim success on [issue #782](https://github.com/Zennay/RaiseAI/issues/782) without physical Watch 7 paired-phone audio evidence.

## Features and security boundary

- Dedicated source namespace `nl.zennay.raiseai.phone` but **application ID `nl.zennay.raiseai` intentionally matches the Watch** for future Google Wear Data Layer. Google requires both the same app ID **and APK signing identity** across Watch and phone; the foreground phone-side receiver is implemented in the stacked branch, but a Watch sender and any audio transport are **not wired yet**. A phone build MUST NOT be installed on the Watch.
- Phone manifest contains **no** requested Android permissions; no network, mic, accessibility, background starts or notifications. Only the companion UI is exported.
- The phone UI now offers **Check paired Watch**, using the official Play Services Wear NodeClient to report current nearby/connected nodes. Device discovery is not signing or user-identity attestation.
- While the phone companion **Activity is foreground**, a narrowly scoped Wear MessageClient listener accepts only the `/raiseai/official-chatgpt/request-v1` endpoint and the existing 96-byte canonical bounded request packet from PR #789. It refuses stale/invalid packets and anything except the **single currently nearby connected Wear node**. Incoming requests never start activities, access the microphone or create a background service; leaving the phone screen unregisters the listener and forgets pending requests. A visible Reject button discards a request; an automatic monotonic UI deadline clears the pending consent prompt instead of leaving a stale approval on screen.
- A pending Watch request needs a **second explicit tap on the phone** within 15 seconds, independently trusted official-publisher certificate SHA-256, policy replay/cooldown authorization and fresh PackageManager signing verification at the actual public launch. Expired/unverified requests fail closed.
- **This is receiver-side code only.** A user-visible Watch sender, Data Layer delivery confirmation, matching APK signing identity, and physical verification must be integrated separately. Do not present this as working Watch→phone launch, automatic Voice startup or Watch↔phone audio bridging.
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

## Foreground-only Watch handoff contract (development)

The receiver subscribes to the literal Wear URI `wear://*/raiseai/official-chatgpt/request-v1` only while `PhoneCompanionActivity` is started. The canonical payload is `r1|OPEN_OFFICIAL_CHATGPT_APP|<32 lowercase hex request ID>|<positive epoch milliseconds>` (<=96 bytes, as defined by the existing PR #789 wire codec). This is **not** an Android intent, deep link, login credential or media packet. Data Layer package+signing parity is a prerequisite; transport identity is checked against a single nearby connected node. A sender has not yet been connected to a Watch user-facing entry point. No permission to start background apps is requested. Google Play Services Wearable dependency is pinned to `20.0.1`; no additional Android manifest permissions are declared.

A future sender must generate cryptographically random request IDs, send only after an intentional Watch user gesture, surface delivery failures truthfully, and avoid storing account data. No claim of delivery, authenticated ChatGPT account Voice, or speaker/mic routing is made here.
