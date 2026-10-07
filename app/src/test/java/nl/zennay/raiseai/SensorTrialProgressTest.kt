package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SensorTrialProgressTest {
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

    @Test
    fun rejectedUnknownLabelCannotContaminateEvidenceIdentity() {
        val progress = SensorTrialRecorder.progressFromLines(
            sequenceOf(
                HEADER,
                row(label = "mouth_raise", revision = REV_A),
                row(label = "unexpected", revision = REV_B)
            )
        )

        assertEquals(1, progress.mouthTrials)
        assertEquals(1, progress.rejectedTrials)
        assertFalse(progress.mixedEvidenceIdentity)
    }

    @Test
    fun rejectedShortTrialCannotContaminateEvidenceIdentity() {
        val progress = SensorTrialRecorder.progressFromLines(
            sequenceOf(
                HEADER,
                row(label = "mouth_raise", revision = REV_A),
                row(label = "view_time", revision = REV_B, durationMs = 2_999)
            )
        )

        assertEquals(1, progress.mouthTrials)
        assertEquals(0, progress.nonTriggerTrials)
        assertEquals(1, progress.rejectedTrials)
        assertFalse(progress.mixedEvidenceIdentity)
    }

    @Test
    fun duplicateAcceptedSessionCannotInflateTrialCounts() {
        val progress = SensorTrialRecorder.progressFromLines(
            sequenceOf(
                HEADER,
                row(label = "mouth_raise", revision = REV_A, sessionId = 42),
                row(label = "mouth_raise", revision = REV_A, sessionId = 42)
            )
        )

        assertEquals(1, progress.mouthTrials)
        assertEquals(1, progress.rejectedTrials)
        assertFalse(progress.mixedEvidenceIdentity)
    }

    @Test
    fun rejectedRowDoesNotReserveSessionIdForLaterValidEvidence() {
        val progress = SensorTrialRecorder.progressFromLines(
            sequenceOf(
                HEADER,
                row(label = "unexpected", revision = REV_B, sessionId = 42),
                row(label = "mouth_raise", revision = REV_A, sessionId = 42)
            )
        )

        assertEquals(1, progress.mouthTrials)
        assertEquals(1, progress.rejectedTrials)
        assertFalse(progress.mixedEvidenceIdentity)
    }

    @Test
    fun acceptedTrialsFromDifferentIdentitiesStillFailMixedEvidenceGate() {
        val progress = SensorTrialRecorder.progressFromLines(
            sequenceOf(
                HEADER,
                row(label = "mouth_raise", revision = REV_A),
                row(label = "view_time", revision = REV_B)
            )
        )

        assertEquals(1, progress.mouthTrials)
        assertEquals(1, progress.nonTriggerTrials)
        assertTrue(progress.mixedEvidenceIdentity)
    }

    private fun row(
        label: String,
        revision: String,
        sessionId: Long = 1,
        durationMs: Long = 3_000,
        samples: Int = 20
    ): String =
        "$label,$sessionId,$durationMs,$samples,false,0.98,1.5.2,$revision,raise-detector-v1"

    companion object {
        private const val HEADER =
            "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity,app_version,source_revision,detector_config"
        private const val REV_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        private const val REV_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    }
}
