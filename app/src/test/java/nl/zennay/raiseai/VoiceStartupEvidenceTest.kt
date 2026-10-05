package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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

    @Test
    fun boundsHistoryToNewestSamples() {
        val existing = (1..50).map { """{"sample":$it}""" }

        val result = VoiceStartupEvidence.boundedHistory(
            existingLines = existing,
            newLine = """{"sample":51}"""
        )

        assertEquals(VoiceStartupEvidence.MAX_HISTORY_SAMPLES, result.size)
        assertFalse(result.contains("""{"sample":1}"""))
        assertEquals("""{"sample":2}""", result.first())
        assertEquals("""{"sample":51}""", result.last())
    }

    @Test
    fun historyDropsBlankLinesAndTrimsNewSample() {
        val result = VoiceStartupEvidence.boundedHistory(
            existingLines = listOf("", """{"sample":1}""", "   "),
            newLine = "  {"sample":2}  ",
            maxSamples = 10
        )

        assertEquals(listOf("""{"sample":1}""", """{"sample":2}"""), result)
    }
}
