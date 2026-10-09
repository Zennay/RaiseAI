package nl.zennay.raiseai

/**
 * One screen-awake budget per explicit native voice interaction.
 *
 * startIfAbsent is intentionally idempotent: SpeechRecognizer retries, duplicate
 * ready callbacks, and screen re-rendering must not extend the original deadline.
 * The Activity owner calls finish() only when the interaction actually ends,
 * not while scheduling an automatic listening retry.
 *
 * Android UI flags and Handler scheduling remain the Activity's responsibility.
 */
internal class NativeVoiceAwakeSession {
    private var sessionStartElapsedMs: Long? = null

    fun startIfAbsent(nowElapsedRealtimeMs: Long): Boolean {
        if (nowElapsedRealtimeMs < 0L || sessionStartElapsedMs != null) return false
        sessionStartElapsedMs = nowElapsedRealtimeMs
        return true
    }

    fun remainingMs(state: String?, nowElapsedRealtimeMs: Long): Long =
        sessionStartElapsedMs?.let { started ->
            NativeVoiceScreenAwakePolicy.remainingAwakeMs(
                state, nowElapsedRealtimeMs, started
            )
        } ?: 0L

    fun shouldKeepScreenAwake(state: String?, nowElapsedRealtimeMs: Long): Boolean =
        remainingMs(state, nowElapsedRealtimeMs) > 0L

    fun finish() {
        sessionStartElapsedMs = null
    }
}
