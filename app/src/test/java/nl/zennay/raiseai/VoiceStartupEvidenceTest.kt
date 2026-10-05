package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class VoiceStartupEvidenceTest {
    @Test
    fun computesElapsedReadyLatency() {
        assertEquals(240L, VoiceStartupEvidence.elapsedMs(1_000L, 1_240L))
    }

    @Test
    fun clampsClockAnomalyToZero() {
        assertEquals(0L, VoiceStartupEvidence.elapsedMs(1_240L, 1_000L))
    }
}
