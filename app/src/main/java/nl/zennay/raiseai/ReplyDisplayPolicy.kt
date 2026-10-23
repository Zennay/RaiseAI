package nl.zennay.raiseai

/**
 * Untrusted model text is display data, never markup or an instruction.
 *
 * This pure policy bounds the text sent to compact Watch UI widgets. Callers should
 * still use TextView.text (not HTML parsing) when displaying the returned string.
 * No network, logging or persistence is performed here.
 */
internal object ReplyDisplayPolicy {
    const val MAX_CODE_POINTS = 2_000
    private const val ELLIPSIS = "…"

    fun forWatch(raw: String?): String? {
        if (raw.isNullOrBlank()) return null
        val output = StringBuilder()
        var index = 0
        var count = 0
        var clipped = false
        while (index < raw.length) {
            val cp = Character.codePointAt(raw, index)
            index += Character.charCount(cp)
            // Reject controls, format controls (including bidi overrides), surrogates
            // and noncharacters; preserve normal newlines and tabs as layout breaks.
            if (cp == 0x0A || cp == 0x09) {
                if (count < MAX_CODE_POINTS) {
                    output.appendCodePoint(cp)
                    count++
                } else clipped = true
                continue
            }
            val type = Character.getType(cp)
            if (type == Character.CONTROL.toInt() ||
                type == Character.FORMAT.toInt() ||
                type == Character.SURROGATE.toInt() ||
                cp == 0xFFFE || cp == 0xFFFF ||
                (cp and 0xFFFF) == 0xFFFE || (cp and 0xFFFF) == 0xFFFF
            ) continue
            if (count >= MAX_CODE_POINTS) {
                clipped = true
                break
            }
            output.appendCodePoint(cp)
            count++
        }
        val result = output.toString().trim()
        if (result.isEmpty()) return null
        return if (clipped) result + ELLIPSIS else result
    }
}
