package nl.zennay.raiseai

enum class ResponseMode {
    SILENT,
    SHORT_SPOKEN,
    FULL_SPOKEN;

    fun next(): ResponseMode = when (this) {
        SILENT -> SHORT_SPOKEN
        SHORT_SPOKEN -> FULL_SPOKEN
        FULL_SPOKEN -> SILENT
    }

    companion object {
        fun fromStored(value: String?): ResponseMode =
            when (value) {
                null -> SHORT_SPOKEN  // New installations answer aloud by default.
                else -> entries.firstOrNull { it.name == value } ?: SILENT
            }
    }
}

object SpokenReplyPolicy {
    private const val SHORT_MAX_CHARS = 220

    fun textFor(mode: ResponseMode, answer: String?): String? {
        val normalized = answer
            ?.replace(Regex("\\s+"), " ")
            ?.trim()
            .orEmpty()

        if (normalized.isBlank()) return null

        return when (mode) {
            ResponseMode.SILENT -> null
            ResponseMode.FULL_SPOKEN -> normalized
            ResponseMode.SHORT_SPOKEN -> shortReply(normalized)
        }
    }

    private fun shortReply(answer: String): String {
        // A decimal point is not a sentence boundary ("2.5 uur", "3.14").
        val sentenceEnd = answer.indices.firstOrNull { index ->
            when (answer[index]) {
                '!', '?' -> true
                '.' -> {
                    val decimal = index > 0 && index < answer.lastIndex &&
                        answer[index - 1].isDigit() && answer[index + 1].isDigit()
                    !decimal
                }
                else -> false
            }
        }

        val firstSentence = sentenceEnd?.let { answer.substring(0, it + 1) } ?: answer
        if (firstSentence.length <= SHORT_MAX_CHARS) return firstSentence

        val clipped = firstSentence.take(SHORT_MAX_CHARS)
        val lastSpace = clipped.lastIndexOf(' ')
        return (if (lastSpace >= 80) clipped.take(lastSpace) else clipped).trimEnd() + "…"
    }
}
