package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RaiseGestureDetectorTest {
    @Test
    fun `still mouth pose alone does not trigger without recent movement`() {
        val detector = RaiseGestureDetector().apply {
            similarityThreshold = 0.95f
            holdMs = 100
        }
        val mouth = MouthPose(0f, 0f, 1f)
        var triggered = false
        for (t in 0L..500L step 50L) {
            triggered = triggered || detector.onAccelerometer(0f, 0f, 9.81f, t, mouth).triggered
        }
        assertFalse(triggered)
    }

    @Test
    fun `movement followed by calibrated pose can trigger`() {
        val detector = RaiseGestureDetector().apply {
            similarityThreshold = 0.94f
            movementThreshold = 0.8f
            holdMs = 100
            cooldownMs = 1_000
        }
        val mouth = MouthPose(0f, 0f, 1f)
        detector.onAccelerometer(0f, 0f, 9.81f, 0, mouth)
        detector.onAccelerometer(4f, 0f, 12f, 50, mouth)

        var triggered = false
        for (t in 100L..500L step 50L) {
            triggered = triggered || detector.onAccelerometer(0f, 0f, 9.81f, t, mouth).triggered
        }
        assertTrue(triggered)
    }

    @Test
    fun `detector cannot retrigger until wrist leaves mouth pose`() {
        val detector = RaiseGestureDetector().apply {
            similarityThreshold = 0.94f
            rearmSimilarityThreshold = 0.90f
            movementThreshold = 0.8f
            holdMs = 100
            cooldownMs = 300
            rearmHoldMs = 200
        }
        val mouth = MouthPose(0f, 0f, 1f)

        detector.onAccelerometer(0f, 0f, 9.81f, 0, mouth)
        detector.onAccelerometer(4f, 0f, 12f, 50, mouth)
        var firstTriggered = false
        for (t in 100L..500L step 50L) {
            firstTriggered = firstTriggered || detector.onAccelerometer(0f, 0f, 9.81f, t, mouth).triggered
        }
        assertTrue(firstTriggered)

        // More movement while still in the mouth pose must not trigger again.
        var retriggeredAtMouth = false
        detector.onAccelerometer(4f, 0f, 12f, 700, mouth)
        for (t in 750L..1_300L step 50L) {
            retriggeredAtMouth = retriggeredAtMouth || detector.onAccelerometer(0f, 0f, 9.81f, t, mouth).triggered
        }
        assertFalse(retriggeredAtMouth)

        // Leave the mouth pose long enough to re-arm.
        for (t in 1_350L..1_800L step 50L) {
            detector.onAccelerometer(9.81f, 0f, 0f, t, mouth)
        }

        detector.onAccelerometer(4f, 0f, 12f, 1_900, mouth)
        var secondTriggered = false
        for (t in 1_950L..2_500L step 50L) {
            secondTriggered = secondTriggered || detector.onAccelerometer(0f, 0f, 9.81f, t, mouth).triggered
        }
        assertTrue(secondTriggered)
    }
}
