package nl.zennay.raiseai

internal class VoiceRetryPolicy(
    private val maxAutomaticRetries: Int = 1
) {
    init {
        require(maxAutomaticRetries >= 0) { "maxAutomaticRetries must be >= 0" }
    }

    private var automaticRetriesUsed = 0

    fun tryConsumeRetry(): Boolean {
        if (automaticRetriesUsed >= maxAutomaticRetries) return false
        automaticRetriesUsed += 1
        return true
    }
}
