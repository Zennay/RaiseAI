package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** JVM-only rehearsal of the prospective SensorEvent -> policy -> detector integration. */
class AccelerometerEventStreamIntegrationTest {
    @Test
    fun filteredDuplicateAndReorderedReadingsDoNotBreakAValidRaise() {
        val policy = AccelerometerEventOrderPolicy()
        val detector = RaiseGestureDetector().apply {
            similarityThreshold = 0.94f
            movementThreshold = 0.7f
            approachStartSimilarityThreshold = 0.94f
            minimumApproachRise = 0.02f
            requiredMovementHits = 2
            holdMs = 100L
            cooldownMs = 1_000L
        }
        val pose = MouthPose(0f, 0f, 1f)
        val baseNs = 20_000_000_000L
        var accepted = 0

        fun deliver(
            x: Float,
            y: Float,
            z: Float,
            timeMs: Long,
            arrivalMs: Long = timeMs + 250L
        ): Boolean {
            val timestampNs = baseNs + timeMs * 1_000_000L
            // Arrival time must never move backwards for an out-of-order sensor batch.
            val nowNs = baseNs + arrivalMs * 1_000_000L
            if (!policy.accept(floatArrayOf(x, y, z), timestampNs, nowNs)) return false
            accepted++
            return detector.onAccelerometer(x, y, z, timeMs, pose).triggered
        }

        for (time in 0L..400L step 50L) {
            assertFalse(deliver(9.81f, 0f, 0f, time))
        }
        deliver(7f, 0f, 7f, 450L)
        val beforeBadBatch = accepted

        // These can occur in a broken/replayed batch, but must never perturb detector state.
        assertFalse(deliver(7f, 0f, 7f, 450L))
        assertFalse(deliver(0f, 0f, 9.81f, 425L, arrivalMs = 700L))
        assertFalse(deliver(Float.NaN, 0f, 9.81f, 475L, arrivalMs = 725L))
        // A finite overflow spike is no safer than NaN: reject before gravity/filter state.
        assertFalse(deliver(Float.MAX_VALUE, 0f, 9.81f, 480L, arrivalMs = 725L))
        assertFalse(deliver(400f, 400f, 0f, 485L, arrivalMs = 725L))
        assertEquals(beforeBadBatch, accepted)

        deliver(4f, 0f, 10f, 500L)
        var triggered = false
        for (time in 550L..1_500L step 50L) {
            triggered = triggered || deliver(0f, 0f, 9.81f, time)
        }

        assertTrue("Valid rise should still reach detector despite bad batch", triggered)
    }

    @Test
    fun oldBufferedBatchCannotMakeItIntoTheDetector() {
        val policy = AccelerometerEventOrderPolicy()
        val nowNs = 70_000_000_000L
        val candidates = listOf(nowNs - 20_000_000_000L, nowNs - 12_000_000_000L)
        var forwarded = 0

        candidates.forEach { timestamp ->
            if (policy.accept(floatArrayOf(0f, 0f, 9.81f), timestamp, nowNs)) {
                forwarded++
            }
        }
        assertEquals(0, forwarded)
        assertTrue(policy.accept(floatArrayOf(0f, 0f, 9.81f), nowNs - 250_000_000L, nowNs))
    }

    @Test
    fun listenerReregistrationCanStartFreshAfterUnregisterReset() {
        val policy = AccelerometerEventOrderPolicy()
        val event = floatArrayOf(0f, 0f, 9.81f)
        assertTrue(policy.accept(event, 60_000_000_000L, 60_000_000_000L))
        assertFalse(policy.accept(event, 59_000_000_000L, 60_000_000_000L))
        policy.reset()
        assertTrue(policy.accept(event, 59_000_000_000L, 60_000_000_000L))
    }
}
