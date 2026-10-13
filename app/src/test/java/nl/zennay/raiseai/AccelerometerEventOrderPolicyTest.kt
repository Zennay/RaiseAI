package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccelerometerEventOrderPolicyTest {
    private val policy = AccelerometerEventOrderPolicy()
    private val gravity = floatArrayOf(0f, 0f, 9.81f)
    private val now = 20_000_000_000L

    @Test
    fun firstValidSampleIsAccepted() {
        assertTrue(policy.accept(gravity, now - 250_000_000L, now))
    }

    @Test
    fun sequentialEventsWithinBatchAreAccepted() {
        assertTrue(policy.accept(gravity, now - 250_000_000L, now))
        assertTrue(policy.accept(gravity, now - 150_000_000L, now))
        assertTrue(policy.accept(gravity, now - 50_000_000L, now))
    }

    @Test
    fun duplicateTimestampCannotReplayDetectorMovement() {
        assertTrue(policy.accept(gravity, now - 1_000_000L, now))
        assertFalse(policy.accept(gravity, now - 1_000_000L, now))
    }

    @Test
    fun outOfOrderSampleCannotRewindGestureWindows() {
        assertTrue(policy.accept(gravity, now - 100_000_000L, now))
        assertFalse(policy.accept(gravity, now - 200_000_000L, now))
        assertTrue(policy.accept(gravity, now - 50_000_000L, now))
    }

    @Test
    fun staleSampleIsRejectedEvenWhenItIsFirst() {
        assertFalse(policy.accept(gravity, now - AccelerometerEventOrderPolicy.MAX_SAMPLE_AGE_NS - 1L, now))
        assertTrue(policy.accept(gravity, now - AccelerometerEventOrderPolicy.MAX_SAMPLE_AGE_NS, now))
    }

    @Test
    fun slightlyFutureTimestampAllowsSchedulingSkew() {
        assertTrue(policy.accept(gravity, now + AccelerometerEventOrderPolicy.MAX_FUTURE_SKEW_NS, now))
    }

    @Test
    fun distantFutureTimestampIsRejectedWithoutConsumingSequence() {
        assertFalse(policy.accept(gravity, now + AccelerometerEventOrderPolicy.MAX_FUTURE_SKEW_NS + 1L, now))
        assertTrue(policy.accept(gravity, now - 1_000_000L, now))
    }

    @Test
    fun invalidClocksAreRejected() {
        assertFalse(policy.accept(gravity, 0L, now))
        assertFalse(policy.accept(gravity, -1L, now))
        assertFalse(policy.accept(gravity, 1L, 0L))
        assertFalse(policy.accept(gravity, 1L, -1L))
    }

    @Test
    fun missingAndShortSensorArraysCannotCrashDetector() {
        assertFalse(policy.accept(null, now, now))
        assertFalse(policy.accept(floatArrayOf(), now, now))
        assertFalse(policy.accept(floatArrayOf(1f, 2f), now, now))
        assertTrue(policy.accept(gravity, now - 1L, now))
    }

    @Test
    fun nonFiniteCoordinatesDoNotPoisonSubsequentSample() {
        val invalid = listOf(
            floatArrayOf(Float.NaN, 0f, 1f),
            floatArrayOf(0f, Float.POSITIVE_INFINITY, 1f),
            floatArrayOf(0f, 0f, Float.NEGATIVE_INFINITY)
        )
        invalid.forEach { assertFalse(policy.accept(it, now - 2L, now)) }
        assertTrue(policy.accept(gravity, now - 2L, now))
    }

    @Test
    fun extraSensorAxesAreAllowedButOnlyFirstThreeAreRequired() {
        assertTrue(policy.accept(floatArrayOf(0f, 0f, 9.81f, Float.NaN), now - 1L, now))
    }

    @Test
    fun resettingAfterUnregistrationStartsFreshStream() {
        assertTrue(policy.accept(gravity, now, now))
        assertFalse(policy.accept(gravity, now - 100_000_000L, now))
        policy.reset()
        assertTrue(policy.accept(gravity, now - 100_000_000L, now))
    }

    @Test
    fun largeElapsedRealtimeValuesDoNotOverflowAgeChecks() {
        val nearMax = Long.MAX_VALUE - 1L
        assertTrue(policy.accept(gravity, nearMax - 1L, nearMax))
        assertFalse(policy.accept(gravity, 1L, nearMax))
    }

    @Test
    fun rejectedOldSampleDoesNotAdvanceLastTimestamp() {
        assertFalse(policy.accept(gravity, now - AccelerometerEventOrderPolicy.MAX_SAMPLE_AGE_NS - 2L, now))
        assertTrue(policy.accept(gravity, now - AccelerometerEventOrderPolicy.MAX_SAMPLE_AGE_NS, now))
    }
}
