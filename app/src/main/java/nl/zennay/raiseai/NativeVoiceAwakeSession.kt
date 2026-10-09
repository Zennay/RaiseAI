package nl.zennay.raiseai

/**
 * One screen-awake budget per explicit native voice interaction.
 *
 * startIfAbsent is intentionally idempotent: SpeechRecognizer retries, duplicate
 * ready callbacks, and screen re-rendering must not extend the original deadline.
 * finish() releases the budget after an interaction, while invalidate() closes
 * the lease permanently when its owning Activity is destroyed.
 *
 * Android UI flags and Handler scheduling remain the Activity's responsibility.
 */
internal class NativeVoiceAwakeSession {
    private var sessionStartElapsedMs: Long? = null
    private var invalidated = false

    fun startIfAbsent(nowElapsedRealtimeMs: Long): Boolean {
        if (invalidated || nowElapsedRealtimeMs < 0L ||
            sessionStartElapsedMs != null
        ) return false

        sessionStartElapsedMs = nowElapsedRealtimeMs
        return true
    }

    fun remainingMs(state: String?, nowElapsedRealtimeMs: Long): Long {
        if (invalidated) return 0L
        return sessionStartElapsedMs?.let { started ->
            NativeVoiceScreenAwakePolicy.remainingAwakeMs(
                state, nowElapsedRealtimeMs, started
            )
        } ?: 0L
    }

    fun shouldKeepScreenAwake(state: String?, nowElapsedRealtimeMs: Long): Boolean =
        remainingMs(state, nowElapsedRealtimeMs) > 0L

    fun finish() {
        sessionStartElapsedMs = null
    }

    fun invalidate() {
        sessionStartElapsedMs = null
        invalidated = true
    }
}
