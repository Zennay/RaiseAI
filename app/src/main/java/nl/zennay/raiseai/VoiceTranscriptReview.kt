package nl.zennay.raiseai

object VoiceTranscriptReview {
    const val AUTO_SUBMIT_DELAY_MS = 1_200L

    data class Pending(
        val transcript: String,
        val autoSubmitDelayMs: Long = AUTO_SUBMIT_DELAY_MS
    )

    fun prepare(rawTranscript: String?): Pending? {
        val normalized = rawTranscript?.trim().orEmpty()
        return normalized.takeIf { it.isNotEmpty() }?.let { Pending(it) }
    }
}
