package nl.zennay.raiseai

/**
 * Launch telemetry must never turn a successful assistant handoff into an app failure.
 * Preference/storage faults are diagnostic failures, not interaction failures.
 */
object AssistantLaunchTelemetry {
    inline fun record(write: () -> Unit) {
        try {
            write()
        } catch (_: RuntimeException) {
            // Best-effort telemetry: preserve the assistant launch result.
        }
    }
}
