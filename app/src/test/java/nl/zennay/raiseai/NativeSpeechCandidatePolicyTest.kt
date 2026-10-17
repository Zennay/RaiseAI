package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NativeSpeechCandidatePolicyTest {
    @Test fun nullResultHasNoTranscript() {
        assertNull(NativeSpeechCandidatePolicy.select(null))
    }

    @Test fun emptyListHasNoTranscript() {
        assertNull(NativeSpeechCandidatePolicy.select(emptyList()))
    }

    @Test fun whollyBlankCandidatesHaveNoTranscript() {
        assertNull(NativeSpeechCandidatePolicy.select(listOf(null, "", " ", "\n\t")))
    }

    @Test fun firstValidCandidateKeepsRecognizerRanking() {
        assertEquals(
            "beste kandidaat",
            NativeSpeechCandidatePolicy.select(
                listOf(" beste kandidaat ", "alternatief", "derde")
            )
        )
    }

    @Test fun blankFirstCandidateFallsBackToUsableAlternative() {
        assertEquals(
            "Kun je het licht aanzetten?",
            NativeSpeechCandidatePolicy.select(
                listOf("", "  ", null, "  Kun je het licht aanzetten?  ", "anders")
            )
        )
    }

    @Test fun internalSpacesAndPunctuationArePreserved() {
        assertEquals(
            "Maak  twee  taken!?",
            NativeSpeechCandidatePolicy.select(
                listOf("  Maak  twee  taken!?  ")
            )
        )
    }

    @Test fun firstUsableHypothesisWinsEvenWhenLaterOneIsLonger() {
        assertEquals(
            "Nee",
            NativeSpeechCandidatePolicy.select(
                listOf(" Nee ", "Nee, ik bedoelde iets anders")
            )
        )
    }
}
