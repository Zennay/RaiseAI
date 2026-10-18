package nl.zennay.raiseai

/**
 * Maps Android SpeechRecognizer RMS callbacks to a safe voice-orb scale.
 *
 * Some recognizers emit NaN or infinity while starting/stopping. Never pass
 * non-finite values to View.scaleX/scaleY: those can corrupt the voice orb's
 * transform and leave the Watch listening feedback invisible.
 *
 * This Android-free policy is prepared for NativeVoiceActivity integration
 * once the active voice lifecycle/callback PRs have settled.
 */
object NativeMicLevelScalePolicy {
    private const val MIN_SCALE = 1f
    private const val MAX_RMS_DB = 10f
    private const val RMS_SCALE_DIVISOR = 45f

    fun scale(rmsDb: Float): Float {
        if (!rmsDb.isFinite()) return MIN_SCALE
        return MIN_SCALE + rmsDb.coerceIn(0f, MAX_RMS_DB) / RMS_SCALE_DIVISOR
    }
}
