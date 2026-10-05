package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ResponseModeTest {
    @Test
    fun responseModesCycleBackToSilent() {
        assertEquals(ResponseMode.SHORT_SPOKEN, ResponseMode.SILENT.next())
        assertEquals(ResponseMode.FULL_SPOKEN, ResponseMode.SHORT_SPOKEN.next())
        assertEquals(ResponseMode.SILENT, ResponseMode.FULL_SPOKEN.next())
    }

    @Test
    fun invalidStoredModeFailsClosedToSilent() {
        assertEquals(ResponseMode.SILENT, ResponseMode.fromStored("UNKNOWN"))
        assertEquals(ResponseMode.SILENT, ResponseMode.fromStored(null))
    }

    @Test
    fun silentModeNeverProducesSpeech() {
        assertNull(SpokenReplyPolicy.textFor(ResponseMode.SILENT, "Dit is een antwoord."))
    }

    @Test
    fun shortModeUsesOnlyFirstSentenceWhenAvailable() {
        assertEquals(
            "Eerste antwoord.",
            SpokenReplyPolicy.textFor(
                ResponseMode.SHORT_SPOKEN,
                "Eerste antwoord. Tweede zin hoeft niet uitgesproken te worden."
            )
        )
    }

    @Test
    fun shortModeBoundsLongSingleSentence() {
        val longAnswer = (1..80).joinToString(" ") { "woord$it" }
        val spoken = SpokenReplyPolicy.textFor(ResponseMode.SHORT_SPOKEN, longAnswer)

        requireNotNull(spoken)
        assert(spoken.length <= 221)
        assert(spoken.endsWith("…"))
    }

    @Test
    fun fullModeNormalizesWhitespaceAndKeepsWholeAnswer() {
        assertEquals(
            "Volledig antwoord met context.",
            SpokenReplyPolicy.textFor(
                ResponseMode.FULL_SPOKEN,
                "  Volledig   antwoord\nmet context.  "
            )
        )
    }
}
