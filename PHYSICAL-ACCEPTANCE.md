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

Before starting the frozen v1.5.2 acceptance session, make `adb devices` show **only the intended Galaxy Watch 7** as an active `device`. Disconnect other ADB phones, emulators or watches for this session. The preserved v1.5.2 evidence-pull scripts predate strict `ANDROID_SERIAL` enforcement, so this one-device condition prevents later diagnostics/trial export from silently selecting another target without changing the frozen artifact.

### Preferred guarded start

From a current RaiseAI checkout, you can first run a non-destructive readiness check:

```bash
bash ./start-frozen-acceptance.command --preflight-only ~/.config/raiseai/watch-gateway.properties
```

A successful preflight prints `FROZEN-ACCEPTANCE PREFLIGHT PASS`. It verifies the single intended Galaxy Watch 7 plus the preserved frozen handoff and provenance chain, then exits **before APK install or physical-session creation**.

When ready for the real session, start the canonical frozen flow with:

```bash
bash ./start-frozen-acceptance.command ~/.config/raiseai/watch-gateway.properties
```

This wrapper fail-closes unless exactly one active ADB device is connected and its model is the intended Galaxy Watch 7 (`SM-L315F` / `SM_L315F`). It then downloads only the preserved Release asset, runs the frozen launcher in verify-only mode, creates a temporary SDK shim with no build-tools so macOS cannot re-sign the APK, binds `ANDROID_SERIAL` to that Watch, and starts the frozen physical-validation flow with a disposable source restore.

If the guarded launcher reaches the on-Watch interaction prompt, sections 2–4 below have already been completed automatically; continue at section 5. The manual steps remain documented as the transparent fallback/debug path.

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

From the extracted artifact directory, use a disposable restore path for the verification pass:

```bash
verify_root="$(mktemp -d)"
RAISE_RESTORE_DIR="$verify_root/source" \
  bash ./start-physical-handoff.command --verify-only
verify_status=$?
rm -rf "$verify_root"
test "$verify_status" -eq 0
```

Continue only after `VERIFY-ONLY PASS`. The verifier checks the bundled source revision, source-bundle SHA-256 and APK identity.

The preserved v1.5.2 launcher predates automatic verify-only cleanup. Running its verify-only mode with the default restore directory would leave `RaiseAI-v1.5.2-source` behind and make the subsequent real start refuse to reuse that path. The disposable override above preserves the frozen artifact exactly while keeping the real acceptance start clean.

## 4. Start the provenance-bound physical session

Use the existing gateway profile. Never paste or commit its token.

The preserved v1.5.2 installer can locally re-sign an APK on macOS when Android build-tools are visible. That is useful for ordinary development upgrades but is **not allowed for this exact-byte acceptance gate**. Run the frozen handoff through a temporary SDK shim that exposes only the already-connected `adb` binary and an empty build-tools directory:

```bash
real_adb="$(command -v adb)"
test -n "$real_adb"

acceptance_root="$(mktemp -d)"
mkdir -p "$acceptance_root/sdk/platform-tools" "$acceptance_root/sdk/build-tools"
ln -s "$real_adb" "$acceptance_root/sdk/platform-tools/adb"

ANDROID_SDK_ROOT="$acceptance_root/sdk" \
RAISE_RESTORE_DIR="$acceptance_root/source" \
  bash ./start-physical-handoff.command ~/.config/raiseai/watch-gateway.properties
acceptance_status=$?

rm -rf "$acceptance_root"
test "$acceptance_status" -eq 0
```

The empty build-tools directory prevents the old launcher from discovering `apksigner`, so the exact frozen APK bytes are passed to `adb install` unchanged. The temporary restore path also makes a failed/retried session start cleanly without mutating the preserved handoff directory.

If installation stops with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, do **not** work around it by re-signing the frozen APK. Exact-byte acceptance requires removing the differently signed old Raise AI installation before retrying; that erases Raise AI app-local data, so do it only as an explicit operator choice.

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

## 7. Record explicit physical quality observations

Issue #34 requires the observed screen-off/background behavior and visible UX failures to be explicit rather than inferred from a passing E2E or reliability score. Before closing the physical gate, create `operator-observations.json` inside the same evidence session directory. Prefer generating the fail-closed template directly from the session identity:

```bash
python3 tools/create-physical-observation-template.py \\
  ~/.raiseai/evidence/<session>/session.json
```

The generator copies the exact Watch/app/source/APK identity, validates the physical-session start timestamp, normalizes `recorded_at_utc` to canonical UTC, refuses timestamps before the session start, and refuses to overwrite an existing observation file. Its three review booleans are deliberately `false` and its behavior fields are blank, so the template cannot pass validation until the real physical checks are completed.

The resulting file has this shape:

```json
{
  "schema_version": 1,
  "recorded_at_utc": "2026-10-06T06:00:00Z",
  "watch_serial": "<same watch_serial as session.json>",
  "app_version": "<same app_version as session.json>",
  "source_revision": "<same source_revision as session.json>",
  "apk_sha256": "<same apk_sha256 as session.json>",
  "screen_off_tested": true,
  "screen_off_behavior": "<what actually happened when tested with the display off>",
  "background_tested": true,
  "background_behavior": "<what actually happened while Raise AI was backgrounded>",
  "ux_failures_reviewed": true,
  "visible_ux_failures": []
}
```

If a visible failure occurred, keep it in `visible_ux_failures`; an empty array means the operator explicitly reviewed the session and observed none. Do not include transcript text, assistant answers, tokens or other secrets.

Validate the record against the same physical session:

```bash
python3 tools/validate-physical-observations.py \
  ~/.raiseai/evidence/<session>/session.json \
  ~/.raiseai/evidence/<session>/operator-observations.json
```

A passing validator means the observation record is complete and provenance-bound. It does **not** turn poor observed behavior into a product pass; failures remain evidence that must be assessed when issue #34 is closed.

## 8. Finish and preserve evidence

The canonical flow writes evidence under:

`~/.raiseai/evidence/<session>/`

A passing session must contain provenance-bound summary evidence including:

- `session.json`
- `e2e-result.json`
- `v1-result.json`
- `operator-observations.json` (local/raw operator record validated by `tools/validate-physical-observations.py`)
- `quality-result.json` (secret-safe provenance/completeness summary suitable for attachment)

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
