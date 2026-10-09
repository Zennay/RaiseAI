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
        require(text.none { it == '\u0000' || (Character.isISOControl(it) && it != '\n' && it != '\r' && it != '\t') }) {
            "assistant_input_control_character"
        }
        // UTF-8 encoders can replace isolated UTF-16 surrogates with '?'. Reject
        // malformed input instead of silently changing a dictated request.
        var index = 0
        while (index < text.length) {
            val current = text[index]
            if (Character.isHighSurrogate(current)) {
                require(index + 1 < text.length && Character.isLowSurrogate(text[index + 1])) {
                    "assistant_input_invalid_unicode"
                }
                index += 2
            } else {
                require(!Character.isLowSurrogate(current)) {
                    "assistant_input_invalid_unicode"
                }
                index++
            }
        }
        require(text.toByteArray(Charsets.UTF_8).size <= MAX_UTF8_BYTES) {
            "assistant_input_too_large"
        }
        return text
    }
}
