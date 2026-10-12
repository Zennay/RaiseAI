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

    fun decide(
        monitoringEnabled: Boolean,
        calibrated: Boolean,
        backgroundLaunchGranted: Boolean
    ): Decision = when {
        !monitoringEnabled -> Decision.SKIP
        !calibrated || !backgroundLaunchGranted -> Decision.DISABLE_UNUSABLE_MONITORING
        else -> Decision.START
    }
}
