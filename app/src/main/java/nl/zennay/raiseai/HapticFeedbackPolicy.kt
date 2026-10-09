package nl.zennay.raiseai

/**
 * Keeps optional haptic feedback from turning a successful raise detection into an app-core
 * failure. Runtime platform failures are recoverable; fatal JVM errors must still propagate.
 */
object HapticFeedbackPolicy {
    fun run(action: () -> Unit): Boolean =
        try {
            action()
            true
        } catch (_: RuntimeException) {
            false
        }
}
