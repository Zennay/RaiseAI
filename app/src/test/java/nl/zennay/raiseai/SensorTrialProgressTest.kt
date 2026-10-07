package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SensorTrialProgressTest {
    private val revisionA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    private val revisionB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    private val detector = "raise-detector-v1;similarity=0.955"

    private fun row(
        label: String,
        sessionId: Long,
        triggered: Boolean,
        durationMs: Long = 4_000L,
        sampleCount: Int = 40,
        revision: String = revisionA
    ): String =
        "$label,$sessionId,$durationMs,$sampleCount,$triggered,0.98,1.5.2,$revision,$detector"

    @Test
    fun roadmapBoundaryPassesAtExactTargets() {
        val progress = SensorTrialProgress(
            mouthTrials = 30,
            mouthDetections = 27,
            nonTriggerTrials = 100,
            falseTriggers = 5
        )

        assertTrue(progress.v1GatePassed)
    }

    @Test
    fun failsBelowDetectionTarget() {
        val progress = SensorTrialProgress(
            mouthTrials = 30,
            mouthDetections = 26,
            nonTriggerTrials = 100,
            falseTriggers = 0
        )

        assertFalse(progress.v1GatePassed)
    }

    @Test
    fun failsAboveFalseTriggerTarget() {
        val progress = SensorTrialProgress(
            mouthTrials = 30,
            mouthDetections = 30,
            nonTriggerTrials = 100,
            falseTriggers = 6
        )

        assertFalse(progress.v1GatePassed)
    }

    @Test
    fun structurallyInvalidEvidenceCanNeverPass() {
        val progress = SensorTrialProgress(
            mouthTrials = 30,
            mouthDetections = 30,
            nonTriggerTrials = 100,
            falseTriggers = 0,
            invalidEvidenceStructure = true
        )

        assertFalse(progress.v1GatePassed)
    }

    @Test
    fun duplicateSessionFailsClosed() {
        val lines = listOf(
            SensorTrialCsvPolicy.HEADER,
            row("mouth_raise", 1, true),
            row("normal_move", 1, false)
        )

        val progress = SensorTrialRecorder.progress(lines)

        assertTrue(progress.invalidEvidenceStructure)
        assertFalse(progress.v1GatePassed)
        assertEquals(1, progress.rejectedTrials)
        assertEquals(0, SensorTrialRecorder.trialCount(lines))
    }

    @Test
    fun malformedRowFailsClosedInsteadOfOnlyReducingDenominator() {
        val lines = listOf(
            SensorTrialCsvPolicy.HEADER,
            row("mouth_raise", 1, true),
            "normal_move,not-a-session,4000,40,false,0.88,1.5.2,$revisionA,$detector"
        )

        val progress = SensorTrialRecorder.progress(lines)

        assertTrue(progress.invalidEvidenceStructure)
        assertFalse(progress.v1GatePassed)
        assertEquals(1, progress.rejectedTrials)
    }

    @Test
    fun shortTrialStillParticipatesInEvidenceIdentity() {
        val lines = listOf(
            SensorTrialCsvPolicy.HEADER,
            row("mouth_raise", 1, true, durationMs = 1_000L, sampleCount = 10, revision = revisionA),
            row("normal_move", 2, false, revision = revisionB)
        )

        val progress = SensorTrialRecorder.progress(lines)

        assertTrue(progress.mixedEvidenceIdentity)
        assertEquals(1, progress.rejectedTrials)
        assertFalse(progress.v1GatePassed)
    }

    @Test
    fun mixedEvidenceCanNeverPass() {
        val progress = SensorTrialProgress(
            mouthTrials = 40,
            mouthDetections = 40,
            nonTriggerTrials = 120,
            falseTriggers = 0,
            mixedEvidenceIdentity = true
        )

        assertFalse(progress.v1GatePassed)
    }
}
