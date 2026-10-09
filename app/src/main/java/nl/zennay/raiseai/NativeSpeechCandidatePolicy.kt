package nl.zennay.raiseai

/**
 * Picks the highest-ranked usable SpeechRecognizer hypothesis.
 *
 * Android recognizers can return a blank first candidate while later ones
 * contain speech. Rejecting the entire result from firstOrNull() then reports
 * "Geen transcript ontvangen" although a valid alternative was supplied.
 *
 * This helper deliberately does not truncate or rewrite dictation content,
 * beyond the same outer whitespace trim used by NativeVoiceActivity today.
 * Validate the chosen text at the submission boundary separately.
 */
object NativeSpeechCandidatePolicy {
    fun select(candidates: List<String?>?): String? {
        if (candidates == null) return null
        for (candidate in candidates) {
            val cleaned = candidate?.trim()
            if (!cleaned.isNullOrEmpty()) return cleaned
        }
        return null
    }
}
