package nl.zennay.raiseai

/**
 * Keeps asynchronous TTS initialization callbacks from resurrecting a closed or replaced engine.
 * An engine that fails to initialize returns to IDLE so a later manual speak can retry.
 */
internal class TtsStartupGate {
    private enum class State { IDLE, STARTING, READY, CLOSED }

    private var state = State.IDLE
    private var generation = 0L

    fun begin(): Long? {
        if (state != State.IDLE) return null
        state = State.STARTING
        generation += 1
        return generation
    }

    /** Returns true only when this callback belongs to the current engine. */
    fun complete(ticket: Long, successful: Boolean): Boolean {
        if (state != State.STARTING || ticket != generation) return false
        state = if (successful) State.READY else State.IDLE
        return true
    }

    /** Allows retry when an initialized engine subsequently refuses to speak. */
    fun invalidateReady(): Boolean {
        if (state != State.READY) return false
        state = State.IDLE
        generation += 1
        return true
    }

    fun isReady(): Boolean = state == State.READY

    fun close() {
        generation += 1
        state = State.CLOSED
    }
}
