# Official ChatGPT Voice phone handoff — receiver guard (prototype)

This pure Kotlin policy is an **app-core protocol preparation** for [issue #782](https://github.com/Zennay/RaiseAI/issues/782). It is deliberately separate from the completed [phone-only probe](./official-chatgpt-phone-probe.md) and from the frozen v1.5.2 Watch acceptance in #34.

`OfficialChatGptPhoneHandoffPolicy` can authorise **only** opening the verified official Android ChatGPT application's ordinary public launcher on a paired phone. It **cannot** enter Voice, route a Watch microphone stream, return ChatGPT audio, access account conversation data, or satisfy Watch → ChatGPT Voice → Watch acceptance. It is not yet wired to a Wear Data Layer service or an Android-phone companion. **No runtime behaviour changes from this PR alone.**

## Contract for future Android-phone receiver

1. Prove the sender is the genuinely paired and allowed Wear node *using transport-provided identity*, never a `senderId` field inside a message.
2. Obtain explicit, current user consent on the phone. A past request or Watch setting is not consent for arbitrary future launches.
3. Verify the **official app publisher's cryptographic signing identity** and installed package on the phone through supported Android APIs. A package name such as `com.openai.chatgpt` alone is not sufficient.
4. Decode exactly the version-1 command `OPEN_OFFICIAL_CHATGPT_APP`, a 32-character lowercase hex random request ID and an issued-at UTC epoch millisecond timestamp. Do not carry passwords, tokens, audio, transcripts, cookies, personal content, URLs or arbitrary intents.
5. Call the policy once on a serialized per-pair session receiver. It rejects missing authorization, mismatched versions/actions, malformed IDs, duplicate IDs, expired (>15 seconds) or >5-second future clock skew, clock rollback, a three-second app-launch rate limit and replay-cache saturation. Only `OPEN_OFFICIAL_APP` permits a public MAIN/LAUNCHER request.
6. If the public launcher fails, show a **clear local failure**. Do not automate the Voice button via undocumented intents, accessibility, screenshots or private endpoints. Do not silently fall back to separately billed APIs.
7. For any real implementation, establish physical phone and Watch 7 evidence for foreground/permissions, audio routing and observed latency before advertising the feature as working.

## Verification

Pure JUnit 4 regression tests are in `app/src/test/java/nl/zennay/raiseai/OfficialChatGptPhoneHandoffPolicyTest.kt`. They cover authorization, consent, publisher gate, strict schema, expiry, replay, distinct-ID launch flooding, cache overflow, rollback and integer limits. A passing JVM test is **not** a demonstration of Android package attestation or physical Voice transport.
