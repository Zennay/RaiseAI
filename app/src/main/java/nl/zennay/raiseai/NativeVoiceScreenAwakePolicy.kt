package nl.zennay.raiseai

/**
 * Limits how long native dictation may force the Watch screen to remain awake.
 *
 * The Activity currently raises FLAG_KEEP_SCREEN_ON at startup without clearing it
 * after transcription, network send, reply or errors. That can keep the display
 * lit until the user manually leaves the voice screen.
 *
 * This pure policy intentionally uses elapsed real time, not wall-clock time, and
 * rejects clock rollback/invalid origins rather than extending an awake budget.
 */
internal object NativeVoiceScreenAwakePolicy {
    const val MAX_INTERACTIVE_AWAKE_MS = 20_000L

    fun shouldKeepScreenAwake(
        voiceState: String?,
        nowElapsedRealtimeMs: Long,
        startedElapsedRealtimeMs: Long
    ): Boolean {
        if (voiceState != "starting" && voiceState != "listening" &&
            voiceState != "understanding"
        ) return false

        if (nowElapsedRealtimeMs < 0L || startedElapsedRealtimeMs < 0L ||
            nowElapsedRealtimeMs < startedElapsedRealtimeMs
        ) return false

        return nowElapsedRealtimeMs - startedElapsedRealtimeMs < MAX_INTERACTIVE_AWAKE_MS
    }
}
