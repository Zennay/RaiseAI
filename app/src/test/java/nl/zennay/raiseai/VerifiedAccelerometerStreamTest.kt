package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class VerifiedAccelerometerStreamTest {
    private val detector = RaiseGestureDetector()
    private val stream = VerifiedAccelerometerStream(detector)
    private val gravity = floatArrayOf(0f, 0f, 9.81f)
    private val now = 50_000_000_000L

    @Test
    fun invalidFiniteSpikeIsDroppedWithoutPoisoningDetectorGravity() {
        val baseline = requireNotNull(stream.process(gravity, now - 400_000_000L, now, null))
        assertFalse(baseline.triggered)

        assertNull(stream.process(floatArrayOf(Float.MAX_VALUE, 0f, 9.81f), now - 200_000_000L, now, null))
        assertNull(stream.process(floatArrayOf(400f, 400f, 0f), now - 150_000_000L, now, null))

        val recovered = requireNotNull(stream.process(gravity, now - 100_000_000L, now, null))
        assertFalse(recovered.triggered)
        assertEquals(0f, recovered.dynamicAcceleration, 0.0001f)
    }

    @Test
    fun malformedAndOutOfOrderEventsNeverReachDetector() {
        assertNull(stream.process(null, now - 500_000_000L, now, null))
        assertNull(stream.process(floatArrayOf(1f, 2f), now - 500_000_000L, now, null))
        assertNull(stream.process(floatArrayOf(Float.NaN, 0f, 0f), now - 500_000_000L, now, null))
        assertNotNull(stream.process(gravity, now - 500_000_000L, now, null))
        assertNull(stream.process(gravity, now - 500_000_000L, now, null))
        assertNull(stream.process(gravity, now - 600_000_000L, now, null))
        assertNotNull(stream.process(gravity, now - 400_000_000L, now, null))
    }

    @Test
    fun resetAllowsNewRegistrationButNotReplayWithinOneRegistration() {
        assertNotNull(stream.process(gravity, now - 100_000_000L, now, null))
        assertNull(stream.process(gravity, now - 200_000_000L, now, null))
        stream.restartWithFreshDetector(RaiseGestureDetector())
        assertNotNull(stream.process(gravity, now - 200_000_000L, now, null))
    }

    @Test
    fun newSensorRegistrationDiscardsOldDetectorGravityAndMovement() {
        val oldOrientation = floatArrayOf(0f, 0f, 9.81f)
        val newOrientation = floatArrayOf(8f, 0f, 6f)
        assertNotNull(stream.process(oldOrientation, now - 500_000_000L, now, null))
        val previousMovement = requireNotNull(
            stream.process(newOrientation, now - 300_000_000L, now, null)
        )
        assertTrue(previousMovement.dynamicAcceleration > 0f)

        stream.restartWithFreshDetector(RaiseGestureDetector())
        val freshBaseline = requireNotNull(
            stream.process(newOrientation, now - 400_000_000L, now, null)
        )
        assertFalse(freshBaseline.triggered)
        assertEquals(0f, freshBaseline.dynamicAcceleration, 0.0001f)
    }

    @Test
    fun restartingWithSameDetectorFailsWithoutResettingReplayProtection() {
        assertNotNull(stream.process(gravity, now - 100_000_000L, now, null))
        val failed = runCatching { stream.restartWithFreshDetector(detector) }.exceptionOrNull()
        assertTrue(failed is IllegalArgumentException)
        assertNull(stream.process(gravity, now - 200_000_000L, now, null))
        assertNotNull(stream.process(gravity, now - 50_000_000L, now, null))
    }

    @Test
    fun physicallyPlausibleMovementCanStillReachDetector() {
        assertNotNull(stream.process(gravity, now - 400_000_000L, now, null))
        val movement = requireNotNull(
            stream.process(floatArrayOf(6f, 0f, 8f), now - 300_000_000L, now, null)
        )
        assertTrue(movement.dynamicAcceleration > 0f)
    }
}
