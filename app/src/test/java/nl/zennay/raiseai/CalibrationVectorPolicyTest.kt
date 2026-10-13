package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CalibrationVectorPolicyTest {
    @Test
    fun normalizesGravityPoseWithoutChangingItsDirection() {
        val pose = requireNotNull(CalibrationVectorPolicy.normalize(0f, -9.81f, 0f))
        assertEquals(0f, pose.x, 0.00001f)
        assertEquals(-1f, pose.y, 0.00001f)
        assertEquals(0f, pose.z, 0.00001f)
        assertTrue(CalibrationVectorPolicy.isUsableUnitPose(pose))
    }

    @Test
    fun normalizesThreeFourFivePose() {
        val pose = requireNotNull(CalibrationVectorPolicy.normalize(3f, 4f, 0f))
        assertEquals(0.6f, pose.x, 0.00001f)
        assertEquals(0.8f, pose.y, 0.00001f)
        assertEquals(0f, pose.z, 0.00001f)
    }

    @Test
    fun rejectsZeroAndSubThresholdSignals() {
        assertNull(CalibrationVectorPolicy.normalize(0f, 0f, 0f))
        assertNull(CalibrationVectorPolicy.normalize(0.0005f, 0f, 0f))
    }

    @Test
    fun acceptsMinimumMagnitudeBoundary() {
        val pose = CalibrationVectorPolicy.normalize(0.001f, 0f, 0f)
        assertEquals(1f, requireNotNull(pose).x, 0.00001f)
    }

    @Test
    fun rejectsNonFiniteComponentsAcrossAllAxes() {
        for (bad in listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY)) {
            assertNull(CalibrationVectorPolicy.normalize(bad, 9.81f, 0f))
            assertNull(CalibrationVectorPolicy.normalize(0f, bad, 9.81f))
            assertNull(CalibrationVectorPolicy.normalize(0f, 9.81f, bad))
        }
    }

    @Test
    fun rejectsHugeButFiniteOrOverRangeReadings() {
        assertNull(CalibrationVectorPolicy.normalize(Float.MAX_VALUE, 0f, 0f))
        assertNull(CalibrationVectorPolicy.normalize(150f, 150f, 0f))
        assertNull(CalibrationVectorPolicy.normalize(-201f, 0f, 0f))
    }

    @Test
    fun supportsReasonableAccelerometerFullScale() {
        val pose = requireNotNull(CalibrationVectorPolicy.normalize(156f, 0f, 0f))
        assertEquals(1f, pose.x, 0.00001f)
    }

    @Test
    fun rejectsMissingOrCorruptedStoredPose() {
        assertFalse(CalibrationVectorPolicy.isUsableUnitPose(null))
        assertFalse(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(0f, 0f, 0f)))
        assertFalse(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(Float.NaN, 0f, 1f)))
        assertFalse(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(Float.POSITIVE_INFINITY, 0f, 1f)))
        assertFalse(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(Float.MAX_VALUE, 0f, 0f)))
        assertFalse(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(0.8f, 0f, 0f)))
        assertFalse(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(1.05f, 0f, 0f)))
    }

    @Test
    fun acceptsNearUnitStoredPoseWithSmallQuantizationError() {
        assertTrue(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(0f, -1f, 0f)))
        assertTrue(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(0.6f, 0.8f, 0f)))
        assertTrue(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(1.019f, 0f, 0f)))
    }

    @Test
    fun rejectsStoredPoseBeyondAllowedUnitTolerance() {
        assertFalse(CalibrationVectorPolicy.isUsableUnitPose(MouthPose(1.021f, 0f, 0f)))
    }
}
