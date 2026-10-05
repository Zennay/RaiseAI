# Physical V1 acceptance — frozen v1.5.2 handoff

This is the operator runbook for the current Raise AI product gate. It does **not** replace or rebuild the Watch APK.

## Frozen acceptance input

Use only:

- source revision: `8f719bb273f9b997848864f342598e7df5f090e5`
- GitHub Actions run: `37241768528`
- artifact: `RaiseAI-Watch7-v1.5.2-physical-handoff-37241768528`
- artifact id: `11317304352`
- artifact digest: `sha256:867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce`

Do not substitute a newer APK, PR build, or rebuilt local APK. Later repository commits are not acceptance inputs.

## 1. Connect the Galaxy Watch 7

Prerequisites:

- Android SDK Platform-Tools / `adb`.
- Watch and computer on the same Wi-Fi network.
- Developer options enabled on the Watch.
- ADB debugging and Wireless debugging enabled.

On Galaxy Watch, Developer options can be enabled from **Settings → About watch → Software** by tapping **Software version** five times.

For first-time pairing:

```bash
adb pair WATCH_IP:PAIRING_PORT
```

Enter the pairing code shown on the Watch. Then use the separate connection port shown under Wireless debugging:

```bash
adb connect WATCH_IP:CONNECTION_PORT
adb devices -l
```

The pairing port and connection port can differ. If the Watch cannot be reached, confirm both devices are on the same non-isolated Wi-Fi network, then retry after:

```bash
adb kill-server
adb start-server
```

## 2. Fetch the exact preserved handoff

The canonical frozen bytes are preserved as GitHub Release asset `611084738` under tag
`physical-handoff-v1.5.2-8f719bb`. From any current RaiseAI checkout, use the
fetcher below. The checkout only supplies the fetch tool; it does **not** become
the acceptance source and it does not rebuild the APK.

```bash
python3 tools/fetch-frozen-physical-handoff.py \
  --output ~/Downloads/raiseai-v1.5.2-frozen
cd ~/Downloads/raiseai-v1.5.2-frozen
```

The fetcher downloads only release asset `611084738`, requires archive SHA-256
`867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce`,
rejects unsafe archive paths/symlinks and refuses to overwrite an existing output
directory.

If the preserved Release asset is temporarily unavailable and the original
Actions artifact is still retained, the original artifact is an equivalent
byte source:

```bash
mkdir -p ~/Downloads/raiseai-v1-acceptance
gh run download 37241768528 \
  --repo Zennay/RaiseAI \
  --name RaiseAI-Watch7-v1.5.2-physical-handoff-37241768528 \
  --dir ~/Downloads/raiseai-v1-acceptance
cd ~/Downloads/raiseai-v1-acceptance
```

## 3. Verify before installing

From the extracted artifact directory:

```bash
bash ./start-physical-handoff.command --verify-only
```

Continue only after `VERIFY-ONLY PASS`. The verifier checks the bundled source revision, source-bundle SHA-256 and APK identity.

## 4. Start the provenance-bound physical session

Use the existing gateway profile. Never paste or commit its token.

```bash
bash ./start-physical-handoff.command ~/.config/raiseai/watch-gateway.properties
```

The command restores the exact bundled source, installs the frozen APK, binds the session to the selected Watch, provisions the gateway profile and then runs the canonical physical-validation flow.

Do not switch Watch, APK, source revision or gateway profile midway through the session.

## 5. Prove Watch → VPS → provider → Watch

When the command pauses:

1. On the Watch, open Native Raise AI.
2. Ask one short ordinary AI question.
3. Wait until a real answer returns on the Watch.
4. Return to the terminal and continue.

The E2E validator must pass on route `quick_ai`, require a real answer, and match the exact app version + source revision from this session.

## 6. Collect the V1 reliability set

Using the same prepared session and installed build, collect:

- at least **30 intentional raise-to-mouth trials**;
- at least **100 representative non-trigger trials**.

The non-trigger set should include normal time-check raises, walking/arm swing, reaching, drinking and other ordinary movements likely to resemble the gesture.

Working pass targets:

- intentional detection rate ≥ **90%**;
- false-trigger rate ≤ **5%**.

Record failures as failures. Do not discard missed raises or false triggers merely to satisfy the threshold.

## 7. Finish and preserve evidence

The canonical flow writes evidence under:

`~/.raiseai/evidence/<session>/`

A passing session must contain provenance-bound summary evidence including:

- `session.json`
- `e2e-result.json`
- `v1-result.json`

Keep the raw trace/trial evidence from that same session. Do **not** upload gateway profiles, tokens, provider credentials, transcript text, or assistant response text.

Attach or link the resulting safe evidence to GitHub issue #34. PR #35 (battery evidence) and PR #36 (acceptance reporter) remain downstream and intentionally unmerged until this physical gate is complete.

## Stop conditions

Stop and fix the session instead of continuing if any of these occur:

- `--verify-only` does not pass;
- the selected ADB target is not the intended Galaxy Watch;
- installed version/source identity does not match the frozen handoff;
- E2E evidence is stale, missing, or from a different source revision;
- the Watch disconnects and the session can no longer prove target identity;
- trial evidence comes from another build/session.

## Legacy note

`DEVICE-TEST.md` documents the older Gemini-first V0.3 flow. It is useful historical context, but it is **not** the canonical V1 acceptance runbook. The native Watch → VPS → provider → Watch path above is the current product gate.
