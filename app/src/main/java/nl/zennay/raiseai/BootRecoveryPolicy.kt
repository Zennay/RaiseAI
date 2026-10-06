package nl.zennay.raiseai

internal object BootRecoveryPolicy {
    private const val ACTION_BOOT_COMPLETED = "android.intent.action.BOOT_COMPLETED"
    private const val ACTION_MY_PACKAGE_REPLACED = "android.intent.action.MY_PACKAGE_REPLACED"

    fun isRecoveryAction(action: String?): Boolean =
        when (action) {
            ACTION_BOOT_COMPLETED,
            ACTION_MY_PACKAGE_REPLACED -> true
            else -> false
        }

    fun shouldStart(
        action: String?,
        monitoringEnabled: Boolean,
        calibrated: Boolean
    ): Boolean =
        isRecoveryAction(action) &&
            monitoringEnabled &&
            calibrated
}
