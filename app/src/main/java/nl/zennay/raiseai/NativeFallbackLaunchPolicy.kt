package nl.zennay.raiseai

internal enum class NativeFallbackLaunchAction {
    FINISH_NATIVE_VOICE,
    KEEP_RECOVERY_UI
}

internal object NativeFallbackLaunchPolicy {
    fun actionFor(launchSucceeded: Boolean): NativeFallbackLaunchAction =
        if (launchSucceeded) {
            NativeFallbackLaunchAction.FINISH_NATIVE_VOICE
        } else {
            NativeFallbackLaunchAction.KEEP_RECOVERY_UI
        }
}
