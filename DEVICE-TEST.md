# Watch 7 test checklist — V0.3

> **Historical fallback checklist only.** Do not use this V0.3 Gemini-first checklist for the current physical acceptance gate. The only valid acceptance carrier is the preserved Raise AI v1.5.2 handoff from source `8f719bb273f9b997848864f342598e7df5f090e5`, GitHub Release tag `physical-handoff-v1.5.2-8f719bb`, Release asset id `611084738`, archive digest `sha256:867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce`. Start it with `bash ./start-frozen-acceptance.command [gateway-profile]` as documented in `START-HERE.md` and `PHYSICAL-ACCEPTANCE.md`. Any different carrier or rebuilt APK is not acceptance evidence.

Record facts, not guesses.

## A. Gemini voice path

- [ ] Open Raise AI.
- [ ] Tap **Test Gemini voice**.
- [ ] Gemini opens.
- [ ] Note whether Gemini is already listening or needs another tap.
- [ ] Check the on-screen **Assistant route** value: `VOICE_COMMAND`, `ASSIST`, or `NONE`.

Result / notes:

## B. Gemini AI answer

- [ ] Tap **Test AI question**.
- [ ] Ask: `Wat is 7 keer 8? Geef alleen het antwoord.`
- [ ] Gemini returns an AI answer.

Result / notes:

## C. Google Home through Gemini

Prerequisite: finish `GEMINI-HOME-SETUP.md` on the paired phone.

- [ ] Tap **Test Google Home command**.
- [ ] Ask Gemini to control a real, harmless device in your home, for example a light.
- [ ] Confirm the physical device actually changed state.
- [ ] Ask Gemini to reverse the action.

Device tested: __________
Worked: yes / no

Do not use security-sensitive devices as the first test.

## D. Calibration

- [ ] Tap **Calibrate mouth pose**.
- [ ] Raise naturally during countdown.
- [ ] Hold watch near mouth during **Hold…**.
- [ ] Status becomes **✓ Calibrated**.

## E. Foreground gesture

- [ ] Enable monitoring.
- [ ] Raise watch to mouth 10 times.
- [ ] Count haptics / trigger-counter increments.

Detected: ___ / 10

## F. False positives

With monitoring on, perform each at least 10 times:

- [ ] Check the time normally.
- [ ] Walk with natural arm swing.
- [ ] Reach for an object.
- [ ] Drink from a glass.
- [ ] Cross arms.

False triggers: ___ / ___ movements

## G. Background / screen off

- [ ] Return to watch face.
- [ ] Let screen sleep.
- [ ] Raise to mouth.
- [ ] Haptic occurs / trigger count increases.
- [ ] Gemini opens automatically and listens.

If the trigger count increases but Gemini does not open, the gesture worked and the remaining blocker is Android's background assistant-launch bridge. Tap the persistent notification's **Gemini** action as the fallback.

## H. Sensor evidence

Record several samples in Raise AI:

- [ ] mouth raise
- [ ] check-time raise
- [ ] normal movement

Then run `pull-watch-data.command`.

## I. Diagnostics

After testing, run `pull-diagnostics.command` and keep the generated folder with the test notes.

## J. Battery

For later, compare similar time windows:

- monitoring OFF: start ___% → end ___%
- monitoring ON: start ___% → end ___%
- duration: ___
