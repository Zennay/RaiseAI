package nl.zennay.raiseai

/**
 * Fail closed: starting the sensor service before the assistant has a background launch
 * grant would register gestures that cannot start an AI conversation.
 *
 * Microphone access is deliberately not a prerequisite for Gemini: Google manages its
 * own permission. Native Raise AI requests RECORD_AUDIO in its own voice activity.
 * Usage access only improves session locking; it is not mandatory.
 */
object RaiseMonitoringSetup {
    enum class Result {
        READY,
        NEEDS_CALIBRATION,
        NEEDS_BACKGROUND_GRANT
    }

    fun check(calibrated: Boolean, backgroundLaunchAllowed: Boolean): Result = when {
        !calibrated -> Result.NEEDS_CALIBRATION
        !backgroundLaunchAllowed -> Result.NEEDS_BACKGROUND_GRANT
        else -> Result.READY
    }
}
