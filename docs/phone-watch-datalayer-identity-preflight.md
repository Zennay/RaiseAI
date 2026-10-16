# Watch ↔ phone Data Layer identity preflight

Android Wear Data Layer communication **requires the same application ID and APK signing identity** on both the phone and Watch. The separate [phone companion PR #791](https://github.com/Zennay/RaiseAI/pull/791) therefore uses the Watch's application ID `nl.zennay.raiseai`. Android's own [Data Layer documentation](https://developer.android.com/training/wearables/data/overview) confirms the package and signing restrictions.

For two **already built** APK files, this independent read-only check fails closed unless both cryptographically verified APKs contain exactly the same application ID and one identical signing certificate:

```bash
python3 tools/verify_phone_watch_datalayer_identity.py \\
  --phone-apk path/to/phone-companion-debug.apk \\
  --watch-apk path/to/watch-debug.apk \\
  --aapt /path/to/android-sdk/build-tools/35.0.0/aapt \\
  --apksigner /path/to/android-sdk/build-tools/35.0.0/apksigner
```

Requirements: Android SDK Build Tools (`aapt` and `apksigner`); two distinct regular, non-symlinked local APK files <=200 MB. Any absent/mismatched, multi-signer, malformed or unverified APK is rejected. It does not install anything, touch a physical Watch or read credentials; the output omits the raw signing fingerprints.

**A successful parity check is not a guarantee of pairing, genuine ChatGPT publisher signing, Watch microphone routing, or actual Voice support.** If signatures differ, rebuild both apps with the same trusted signing key via your existing secure release process; do not export/share a private keystore into logs, chats or repository files, and do not overwrite the frozen physical Watch v1.5.2 acceptance installation ([issue #34](https://github.com/Zennay/RaiseAI/issues/34)). The actual data transport must still be built, connected and physically verified.
