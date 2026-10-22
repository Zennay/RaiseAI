# Raise AI · Wear OS quick-launch Tile

The Galaxy Watch 7 can now add a **Raise AI - snel starten** Tile to the
watch's Tiles carousel. Swiping to it presents two large, deliberate tap targets:

- **Luisteren** opens the existing `NativeVoiceActivity` and asks for microphone
  permission if needed. It uses the configured Raise gateway only after a
  speech result; it does not start listening while the Tile is off-screen.
- **Gemini** opens the existing Google-scoped assistant through
  `AssistantProxyActivity`, preserving its existing fallback handling.

## Add and use

Install a newly built RaiseAI Watch APK from this branch (no APK is installed
merely by merging source). On the Galaxy Watch, open the tile editor from the
Tiles carousel, choose **Add tile**, then **Raise AI - snel starten**. Swipe to
the tile and tap the desired assistant.

## Privacy and battery

The Tile has no sensor callbacks, network polling, scheduled refreshes, or
background microphone. It opens only existing internal activities after a user
tap; all existing recording, Google assistant and gateway permission checks
still apply. The system may bind to the Tile service only through
`com.google.android.wearable.permission.BIND_TILE_PROVIDER`. No new app
permissions or exported activities were added.

The Tile is an *alternate launcher*, not proof of Watch-to-phone ChatGPT
consumer Voice audio streaming, a device-tested gesture milestone or a
replacement for the frozen v1.5.2 physical acceptance gate.

## Integration considerations

- Keep the Tile registered with `androidx.wear.tiles.action.BIND_TILE_PROVIDER`.
- A real Galaxy Watch 7 installation remains necessary before claiming the
  system launcher can activate the two internal activities on the target
  Samsung firmware.
- Existing Android / security / required CI must pass before merge.
