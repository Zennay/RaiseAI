package nl.zennay.raiseai

/**
 * Keeps callbacks from superseded SpeechRecognizer instances from mutating the active voice UI.
 *
 * SpeechRecognizer teardown is asynchronous: an old recognizer may still deliver callbacks after a
 * replacement recognizer has started. Every recognizer gets a monotonically increasing generation,
 * and only the current generation is allowed to update NativeVoiceActivity.
 */
internal class VoiceRecognitionSessionGate {
    private var currentGeneration = 0L

    fun beginSession(): Long {
        currentGeneration += 1
        return currentGeneration
    }

    fun accepts(generation: Long): Boolean =
        generation > 0L && generation == currentGeneration

    fun invalidate(generation: Long) {
        if (generation == currentGeneration) {
            currentGeneration += 1
        }
    }

    fun invalidateAll() {
        currentGeneration += 1
    }
}
