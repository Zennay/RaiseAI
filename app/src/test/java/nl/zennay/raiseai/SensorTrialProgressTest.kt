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
    fun oneRejectedRowBlocksOtherwisePassingEvidence() {
        val progress = SensorTrialProgress(
            mouthTrials = 30,
            mouthDetections = 27,
            nonTriggerTrials = 100,
            falseTriggers = 5,
            rejectedTrials = 1
        )
        assertFalse(progress.v1GatePassed)
    }

    @Test
    fun impossibleCounterPairsCannotPass() {
        assertFalse(
            SensorTrialProgress(
                mouthTrials = 30, mouthDetections = 31,
                nonTriggerTrials = 100, falseTriggers = 0
            ).v1GatePassed
        )
        assertFalse(
            SensorTrialProgress(
                mouthTrials = 30, mouthDetections = 30,
                nonTriggerTrials = 100, falseTriggers = -1
            ).v1GatePassed
        )
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
