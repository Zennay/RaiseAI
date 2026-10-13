# Physical Watch acceptance: reproducible operator worksheet

This worksheet supplements [PHYSICAL-ACCEPTANCE.md](../PHYSICAL-ACCEPTANCE.md) and [issue #34](https://github.com/Zennay/RaiseAI/issues/34). It does not replace the frozen v1.5.2 launcher, verifier, or thresholds. **Do not mark physical acceptance passed from this worksheet alone.**

## Before touching the Watch

- [ ] Run the canonical `start-frozen-acceptance.command --preflight-only` workflow and retain its PASS message.
- [ ] Confirm there is **exactly one** authorized ADB target: the Galaxy Watch 7 (`SM-L315F` or `SM_L315F`).
- [ ] Verify the frozen archive against the hash and source revision specified in issue #34. Never use a repository-tip build, locally re-signed APK or newer artifact as a substitute.
- [ ] Use the canonical launcher to prepare a **new** evidence session. Do not mix records between sessions.
- [ ] Verify Raise AI displays **Calibrated** before collecting detector trials. If needed, perform the one-time mouth-pose calibration first.
- [ ] Note ambient conditions locally (e.g. sleeve, wrist, motion, network state). Do not upload Watch serials, tokens, transcripts or full raw logs.

## Trial execution protocol

Keep the Watch worn normally for the whole run. Make intentional and non-trigger trials representative of real use, rather than tailoring movements to optimize the score.

| Phase | Minimum count | Operator action | Required evidence |
| --- | ---: | --- | --- |
| Native E2E | 1 completed request | Trigger a fresh `quick_ai` request, confirm Watch → VPS gateway → provider/model → Watch response | Canonical `e2e-result.json` from **this** session |
| Intentional raises | 30 | For each trial, use **Record mouth raise · 4 sec**; include unsuccessful activations | All trials, including misses |
| Non-trigger movement | 100 | Use both **Record check-time raise · 4 sec** and **Record normal movement · 4 sec**, reflecting ordinary wrist/arm use | All trials, including false triggers |
| UX/background | Explicit checks | Observe screen-off, background and other visible friction on the physical Watch | Completed `operator-observations.json` locally and validated `quality-result.json` |

Do not discard a failed trial, restart a session to hide failures, or count a duplicate recording as a fresh trial. If calibration, app version, device or source revision changes partway through, abandon that session and start a new provenance-bound session.

## Review and handoff

1. Generate the summaries using the canonical scripts, not hand-written percentages.
2. Validate operator observations against the **same session** and record both positive and negative UX findings.
3. Confirm the working thresholds: **at least 90%** detection across 30 intentional trials, **at most 5%** false triggers across 100 non-trigger trials. These are necessary but not sufficient for closing issue #34.
4. Confirm the exact source/APK identity, a successful real E2E round trip and the required screen-off/background observations.
5. Keep raw `session.json`, Watch serials, operator notes, diagnostics, trace/trial CSVs and credential/transcript/answer content local. Share only the explicitly reviewed, secret-safe summary set defined in `PHYSICAL-ACCEPTANCE.md`; fail-closed bundle preparation is tracked separately in issue #514.
6. Update the canonical issue #34 and Notion Current State only after evidence has been reviewed. If any gate fails or data is missing, record **not passed** and the concrete reason; do not infer success from an automated test run.

**Session record (local only):** session directory ______; frozen source revision ______; verified archive digest ______; Watch model ______; date/time ______; intentional detected/30 ______; false triggers/100 ______; E2E passed? ______; UX/background reviewed? ______; reviewer ______.
