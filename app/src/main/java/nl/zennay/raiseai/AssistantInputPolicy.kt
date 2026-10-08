package nl.zennay.raiseai

/**
 * Pure validation boundary for text submitted from Watch dictation or typed input.
 *
 * Do not truncate input silently: a shortened request can change the user's intent.
 * Callers should show a recoverable validation error rather than send invalid text.
 */
internal object AssistantInputPolicy {
    const val MAX_UTF8_BYTES = 4096

    fun validate(text: String): String {
        require(text.isNotBlank()) { "assistant_input_empty" }
        require(text.none { it == '\u0000' || (it.isISOControl() && it != '\n' && it != '\r' && it != '\t') }) {
            "assistant_input_control_character"
        }
        require(text.toByteArray(Charsets.UTF_8).size <= MAX_UTF8_BYTES) {
            "assistant_input_too_large"
        }
        return text
    }
}
