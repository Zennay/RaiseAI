package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RaiseGestureDetectorTest {
    @Test
    fun stillMouthPoseDoesNotTrigger() {
        val detector = RaiseGestureDetector().apply { similarityThreshold = 0.95f; holdMs = 100 }
        val mouth = MouthPose(0f, 0f, 1f)
        var triggered = false
        for (t in 0L..500L step 50L) {
            triggered = triggered || detector.onAccelerometer(0f, 0f, 9.81f, t, mouth).triggered
        }
        assertFalse(triggered)
    }

    @Test
    fun singleAccelerationSpikeIsNotEnough() {
        val detector = RaiseGestureDetector().apply {
            similarityThreshold = 0.94f
            movementThreshold = 0.8f
            requiredMovementHits = 2
            holdMs = 100
        }
        val mouth = MouthPose(0f, 0f, 1f)
        for (t in 0L..300L step 50L) detector.onAccelerometer(9.81f, 0f, 0f, t, mouth)
        // One isolated bump, then the wrist returns to its original away-from-mouth pose.
        detector.onAccelerometer(3f, 0f, 11f, 350L, mouth)
        var triggered = false
        for (t in 400L..1_000L step 50L) {
            triggered = triggered || detector.onAccelerometer(9.81f, 0f, 0f, t, mouth).triggered
        }
        assertFalse(triggered)
    }

    @Test
    fun movementFromAwayPoseCanTrigger() {
        val detector = RaiseGestureDetector().apply {
            similarityThreshold = 0.94f
            movementThreshold = 0.7f
            approachStartSimilarityThreshold = 0.94f
            minimumApproachRise = 0.02f
            requiredMovementHits = 2
            holdMs = 100
            cooldownMs = 1_000
        }
        val mouth = MouthPose(0f, 0f, 1f)
        for (t in 0L..400L step 50L) detector.onAccelerometer(9.81f, 0f, 0f, t, mouth)
        detector.onAccelerometer(7f, 0f, 7f, 450L, mouth)
        detector.onAccelerometer(4f, 0f, 10f, 500L, mouth)
        var triggered = false
        for (t in 550L..1_500L step 50L) {
            triggered = triggered || detector.onAccelerometer(0f, 0f, 9.81f, t, mouth).triggered
        }
        assertTrue(triggered)
    }
}