package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceTranscriptReviewTest {
    @Test
    fun trimsTranscriptAndKeepsCorrectionWindowShort() {
        val pending = VoiceTranscriptReview.prepare("  zet de lamp aan  ")

        requireNotNull(pending)
        assertEquals("zet de lamp aan", pending.transcript)
        assertEquals(VoiceTranscriptReview.AUTO_SUBMIT_DELAY_MS, pending.autoSubmitDelayMs)
        assertTrue(pending.autoSubmitDelayMs in 500L..1_500L)
    }

    @Test
    fun rejectsBlankTranscript() {
        assertNull(VoiceTranscriptReview.prepare("   "))
        assertNull(VoiceTranscriptReview.prepare(null))
    }
}
