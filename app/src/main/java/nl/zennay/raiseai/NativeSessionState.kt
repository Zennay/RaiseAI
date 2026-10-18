package nl.zennay.raiseai

object NativeSessionState {
    private const val IDLE_STATE = "idle"

    @Volatile
    private var state: String = IDLE_STATE

    fun set(next: String) {
        state = next
    }

    fun get(): String = state

    fun isBusy(): Boolean = blocksGesture(state)

    internal fun blocksGesture(candidate: String): Boolean =
        candidate != IDLE_STATE
}
