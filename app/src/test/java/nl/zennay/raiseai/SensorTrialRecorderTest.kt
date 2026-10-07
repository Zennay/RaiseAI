package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class SensorTrialRecorderTest {
    private val revision = "0123456789abcdef0123456789abcdef01234567"
    private val config = "raise-detector-v1;similarity=0.955"

    private fun row(
        label: String = "mouth_raise",
        sessionId: String = "1234",
        durationMs: String = "3000",
        sampleCount: String = "20",
        triggered: String = "true",
        maxSimilarity: String = "0.97",
        appVersion: String = "1.5.3",
        sourceRevision: String = revision,
        detectorConfig: String = config,
    ): String = listOf(
        label,
        sessionId,
        durationMs,
        sampleCount,
        triggered,
        maxSimilarity,
        appVersion,
        sourceRevision,
        detectorConfig,
    ).joinToString(",")

    @Test
    fun acceptsCompleteQualifyingTrialRow() {
        val progress = SensorTrialRecorder.summarize(sequenceOf(row()))

        assertEquals(1, progress.mouthTrials)
        assertEquals(1, progress.mouthDetections)
        assertEquals(0, progress.rejectedTrials)
        assertFalse(progress.mixedEvidenceIdentity)
    }

    @Test
    fun rejectsMalformedSessionId() {
        val progress = SensorTrialRecorder.summarize(
            sequenceOf(row(sessionId = "not-a-session"))
        )

        assertEquals(0, progress.mouthTrials)
        assertEquals(1, progress.rejectedTrials)
    }

    @Test
    fun rejectsMalformedSimilarity() {
        val progress = SensorTrialRecorder.summarize(
            sequenceOf(row(maxSimilarity = "not-a-number"))
        )

        assertEquals(0, progress.mouthTrials)
        assertEquals(1, progress.rejectedTrials)
    }

    @Test
    fun rejectsNonFiniteSimilarity() {
        for (value in listOf("NaN", "Infinity", "-Infinity")) {
            val progress = SensorTrialRecorder.summarize(
                sequenceOf(row(maxSimilarity = value))
            )

            assertEquals("value=$value", 0, progress.mouthTrials)
            assertEquals("value=$value", 1, progress.rejectedTrials)
        }
    }

    @Test
    fun preservesValidNonTriggerAccounting() {
        val progress = SensorTrialRecorder.summarize(
            sequenceOf(
                row(label = "view_time", triggered = "false"),
                row(label = "normal_move", sessionId = "1235", triggered = "true"),
            )
        )

        assertEquals(2, progress.nonTriggerTrials)
        assertEquals(1, progress.falseTriggers)
        assertEquals(0, progress.rejectedTrials)
    }

    @Test
    fun mixedEvidenceIdentityStillFailsClosed() {
        val progress = SensorTrialRecorder.summarize(
            sequenceOf(
                row(),
                row(sessionId = "1235", sourceRevision = "f".repeat(40)),
            )
        )

        assertEquals(2, progress.mouthTrials)
        assertEquals(0, progress.rejectedTrials)
        assertEquals(true, progress.mixedEvidenceIdentity)
    }
}
