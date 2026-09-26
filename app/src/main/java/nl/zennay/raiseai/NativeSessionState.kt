package nl.zennay.raiseai

object NativeSessionState {
    private val busyStates = setOf(
        "starting",
        "listening",
        "understanding",
        "sending",
        "executing",
        "replying"
    )

    @Volatile
    private var state: String = "idle"

    fun set(next: String) {
        state = next
    }

    fun get(): String = state

    fun isBusy(): Boolean = state in busyStates
}
