package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sqrt

class MouthPoseCalibrationQualityTest {
    @Test
    fun acceptsStableGravityAlignedSamplesAndNormalizesPose() {
        val samples = List(16) { index ->
            val jitter = (index % 4 - 1.5f) * 0.015f
            floatArrayOf(1.2f + jitter, 8.7f - jitter, 4.1f + jitter)
        }

        val result = MouthPoseCalibrationQuality.evaluate(samples)

        assertTrue(result.accepted)
        assertEquals(null, result.failure)
        val pose = assertNotNull(result.pose)
        val length = sqrt(pose!!.x * pose.x + pose.y * pose.y + pose.z * pose.z)
        assertEquals(1.0f, length, 0.0001f)
    }

    @Test
    fun rejectsTooFewSamples() {
        val result = MouthPoseCalibrationQuality.evaluate(
            List(MouthPoseCalibrationQuality.MIN_SAMPLES - 1) {
                floatArrayOf(0f, 9.81f, 0f)
            }
        )

        assertFalse(result.accepted)
        assertEquals(CalibrationFailure.TOO_FEW_SAMPLES, result.failure)
    }

    @Test
    fun rejectsNonFiniteSample() {
        val samples = MutableList(MouthPoseCalibrationQuality.MIN_SAMPLES) {
            floatArrayOf(0f, 9.81f, 0f)
        }
        samples[3] = floatArrayOf(Float.NaN, 9.81f, 0f)

        val result = MouthPoseCalibrationQuality.evaluate(samples)

        assertEquals(CalibrationFailure.INVALID_SAMPLE, result.failure)
    }

    @Test
    fun rejectsImplausibleGravityMagnitude() {
        val result = MouthPoseCalibrationQuality.evaluate(
            List(MouthPoseCalibrationQuality.MIN_SAMPLES) {
                floatArrayOf(0f, 2.0f, 0f)
            }
        )

        assertEquals(CalibrationFailure.GRAVITY_OUT_OF_RANGE, result.failure)
    }

    @Test
    fun rejectsCalibrationWhileArmIsStillMoving() {
        val samples = List(12) { index ->
            if (index % 2 == 0) {
                floatArrayOf(0f, 5.0f, 0f)
            } else {
                floatArrayOf(0f, 14.0f, 0f)
            }
        }

        val result = MouthPoseCalibrationQuality.evaluate(samples)

        assertEquals(CalibrationFailure.TOO_MUCH_MOTION, result.failure)
    }

    @Test
    fun rejectsUnstableOrientationEvenAtNormalGravityMagnitude() {
        val samples = List(12) { index ->
            if (index % 2 == 0) {
                floatArrayOf(9.81f, 0f, 0f)
            } else {
                floatArrayOf(0f, 9.81f, 0f)
            }
        }

        val result = MouthPoseCalibrationQuality.evaluate(samples)

        assertEquals(CalibrationFailure.UNSTABLE_ORIENTATION, result.failure)
    }
}
