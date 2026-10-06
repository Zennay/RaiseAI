package nl.zennay.raiseai

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
    fun rejectedRowsPreventLocalV1PassClaim() {
        val progress = SensorTrialProgress(
            mouthTrials = 30,
            mouthDetections = 30,
            nonTriggerTrials = 100,
            falseTriggers = 0,
            rejectedTrials = 1
        )

        assertFalse(progress.v1GatePassed)
    }

    @Test
    fun duplicateSessionIdIsRejectedAndNotDoubleCounted() {
        val revision = "a".repeat(40)
        val rows = sequenceOf(
            SensorTrialRecorder.HEADER,
            "mouth_raise,1001,4000,40,true,0.98,1.5.3,$revision,raise-detector-v1",
            "mouth_raise,1001,4000,40,true,0.99,1.5.3,$revision,raise-detector-v1"
        )

        val progress = SensorTrialRecorder.summarizeRows(rows)

        assertTrue(progress.mouthTrials == 1)
        assertTrue(progress.mouthDetections == 1)
        assertTrue(progress.rejectedTrials == 1)
        assertFalse(progress.v1GatePassed)
    }

    @Test
    fun nonFiniteSimilarityAndInvalidSessionAreRejected() {
        val revision = "b".repeat(40)
        val rows = sequenceOf(
            SensorTrialRecorder.HEADER,
            "normal_move,0,4000,40,false,0.50,1.5.3,$revision,raise-detector-v1",
            "view_time,1002,4000,40,false,NaN,1.5.3,$revision,raise-detector-v1"
        )

        val progress = SensorTrialRecorder.summarizeRows(rows)

        assertTrue(progress.nonTriggerTrials == 0)
        assertTrue(progress.rejectedTrials == 2)
    }

    @Test
    fun uniqueValidRowsPreserveIdentityAndCounts() {
        val revision = "c".repeat(40)
        val rows = sequenceOf(
            SensorTrialRecorder.HEADER,
            "mouth_raise,2001,4000,40,true,0.98,1.5.3,$revision,raise-detector-v1",
            "view_time,2002,4000,40,false,0.72,1.5.3,$revision,raise-detector-v1",
            "normal_move,2003,4000,40,true,0.81,1.5.3,$revision,raise-detector-v1"
        )

        val progress = SensorTrialRecorder.summarizeRows(rows)

        assertTrue(progress.mouthTrials == 1)
        assertTrue(progress.mouthDetections == 1)
        assertTrue(progress.nonTriggerTrials == 2)
        assertTrue(progress.falseTriggers == 1)
        assertTrue(progress.rejectedTrials == 0)
        assertFalse(progress.mixedEvidenceIdentity)
    }

    @Test
    fun impossibleManualCountsCannotPassGate() {
        assertFalse(
            SensorTrialProgress(
                mouthTrials = 30,
                mouthDetections = 31,
                nonTriggerTrials = 100,
                falseTriggers = 0
            ).v1GatePassed
        )
        assertFalse(
            SensorTrialProgress(
                mouthTrials = 30,
                mouthDetections = 30,
                nonTriggerTrials = 100,
                falseTriggers = 101
            ).v1GatePassed
        )
    }


    @Test
    fun unexpectedCsvHeaderFailsClosed() {
        val revision = "d".repeat(40)
        val progress = SensorTrialRecorder.summarizeRows(
            sequenceOf(
                "label,session_id,wrong_schema",
                "mouth_raise,3001,4000,40,true,0.98,1.5.3,$revision,raise-detector-v1"
            )
        )

        assertTrue(progress.mouthTrials == 0)
        assertTrue(progress.rejectedTrials == 1)
        assertFalse(progress.v1GatePassed)
    }

}
