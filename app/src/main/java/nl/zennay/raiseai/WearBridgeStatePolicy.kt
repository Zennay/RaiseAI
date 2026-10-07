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

    fun stateAfterSpeakingUpdate(speaking: Boolean, connected: Boolean): String =
        if (!connected) "disconnected" else if (speaking) "speaking" else "ready"
}
