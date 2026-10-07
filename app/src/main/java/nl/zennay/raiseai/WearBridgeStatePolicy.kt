package nl.zennay.raiseai

internal object WearBridgeStatePolicy {
    private val gestureReadyStates = setOf("cold", "ready")
    private val inboundStates = setOf(
        "loading",
        "ready",
        "starting",
        "listening",
        "finalizing",
        "sending",
        "speaking",
        "disconnected"
    )

    fun blocksGesture(state: String): Boolean =
        state !in gestureReadyStates

    fun normalizeInboundState(state: String): String =
        state.takeIf { it in inboundStates } ?: "unknown"

    fun acceptsStartRequest(state: String, reason: String, active: Boolean): Boolean {
        if (active) return false
        return reason != "gesture" || !blocksGesture(state)
    }

    fun stateAfterSpeakingUpdate(speaking: Boolean, connected: Boolean): String =
        if (!connected) "disconnected" else if (speaking) "speaking" else "ready"
}
