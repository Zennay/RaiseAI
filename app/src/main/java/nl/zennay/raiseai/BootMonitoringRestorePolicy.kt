package nl.zennay.raiseai

/**
 * Boot/package-upgrade restoration may restart monitoring only when the saved
 * user choice is still actionable. Both supported assistant launchers require
 * the background activity launch grant for a gesture-triggered launch.
 *
 * Keep this policy independent of Android so boot recovery can be tested
 * without starting a real foreground service.
 */
internal object BootMonitoringRestorePolicy {
    enum class Decision {
        SKIP,
        DISABLE_UNUSABLE_MONITORING,
        START
    }

    /**
     * Saved calibration is intended to be a unit gravity vector. Corrupted
     * preferences (NaN, infinities, zero, or hugely out-of-range values) can
     * otherwise keep the detector silently unusable after a reboot.
     */
    fun hasUsableCalibration(pose: MouthPose?): Boolean {
        if (pose == null) return false
        if (!pose.x.isFinite() || !pose.y.isFinite() || !pose.z.isFinite()) return false
        val normSquared = pose.x * pose.x + pose.y * pose.y + pose.z * pose.z
        return normSquared.isFinite() && normSquared in MIN_NORM_SQUARED..MAX_NORM_SQUARED
    }

    fun decide(
        monitoringEnabled: Boolean,
        calibrated: Boolean,
        backgroundLaunchGranted: Boolean,
        accelerometerAvailable: Boolean
    ): Decision = when {
        !monitoringEnabled -> Decision.SKIP
        !calibrated || !backgroundLaunchGranted || !accelerometerAvailable ->
            Decision.DISABLE_UNUSABLE_MONITORING
        else -> Decision.START
    }

    // Tolerate small persisted-float drift; fail closed on implausible vectors.
    private const val MIN_NORM_SQUARED = 0.64f
    private const val MAX_NORM_SQUARED = 1.44f
}
