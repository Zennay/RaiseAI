package nl.zennay.raiseai

internal object WearBridgeStatePolicy {
    private val gestureReadyStates = setOf("cold", "ready")

    fun blocksGesture(state: String): Boolean =
        state !in gestureReadyStates

    fun stateAfterSpeakingUpdate(speaking: Boolean, connected: Boolean): String =
        if (!connected) "disconnected" else if (speaking) "speaking" else "ready"
}
