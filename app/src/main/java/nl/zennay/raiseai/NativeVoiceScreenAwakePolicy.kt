package nl.zennay.raiseai

/**
 * Limits how long native dictation may force the Watch screen to remain awake.
 *
 * The Activity currently raises FLAG_KEEP_SCREEN_ON at startup without clearing it
 * after transcription, network send, reply or errors. That can keep the display
 * lit until the user manually leaves the voice screen.
 *
 * This pure policy uses elapsed real time, not wall-clock time. Its remaining
 * budget is also suitable for scheduling a deadline callback: a static state
 * check alone would never release FLAG_KEEP_SCREEN_ON when recognition stalls.
 */
internal object NativeVoiceScreenAwakePolicy {
    const val MAX_INTERACTIVE_AWAKE_MS = 20_000L

    fun remainingAwakeMs(
        voiceState: String?,
        nowElapsedRealtimeMs: Long,
        startedElapsedRealtimeMs: Long
    ): Long {
        if (voiceState != "starting" && voiceState != "listening" &&
            voiceState != "understanding"
        ) return 0L

        // Fail closed on invalid origin or clock rollback; only subtract after
        // checking monotonic ordering, which also avoids signed overflow.
        if (nowElapsedRealtimeMs < 0L || startedElapsedRealtimeMs < 0L ||
            nowElapsedRealtimeMs < startedElapsedRealtimeMs
        ) return 0L

        val elapsedMs = nowElapsedRealtimeMs - startedElapsedRealtimeMs
        return if (elapsedMs < MAX_INTERACTIVE_AWAKE_MS) {
            MAX_INTERACTIVE_AWAKE_MS - elapsedMs
        } else {
            0L
        }
    }

    fun shouldKeepScreenAwake(
        voiceState: String?,
        nowElapsedRealtimeMs: Long,
        startedElapsedRealtimeMs: Long
    ): Boolean = remainingAwakeMs(voiceState, nowElapsedRealtimeMs, startedElapsedRealtimeMs) > 0L
}
