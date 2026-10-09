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
            entries.firstOrNull { it.name == value } ?: SILENT
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
        val sentenceEnd = answer
            .mapIndexedNotNull { index, char ->
                if (char == '.' || char == '!' || char == '?') index else null
            }
            .firstOrNull()

        val firstSentence = sentenceEnd?.let { answer.substring(0, it + 1) } ?: answer
        if (firstSentence.length <= SHORT_MAX_CHARS) return firstSentence

        val clipped = firstSentence.take(SHORT_MAX_CHARS)
        val lastSpace = clipped.lastIndexOf(' ')
        return (if (lastSpace >= 80) clipped.take(lastSpace) else clipped).trimEnd() + "…"
    }
}
