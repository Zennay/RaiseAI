package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class CalibrationPosePolicyTest {
    @Test
    fun normalizesFinitePose() {
        val pose = CalibrationPosePolicy.normalizeOrNull(3f, 0f, 4f)

        requireNotNull(pose)
        assertEquals(0.6f, pose.x, 0.0001f)
        assertEquals(0f, pose.y, 0.0001f)
        assertEquals(0.8f, pose.z, 0.0001f)
    }

    @Test
    fun rejectsNonFiniteComponents() {
        assertNull(CalibrationPosePolicy.normalizeOrNull(Float.NaN, 0f, 1f))
        assertNull(CalibrationPosePolicy.normalizeOrNull(Float.POSITIVE_INFINITY, 0f, 1f))
        assertNull(CalibrationPosePolicy.normalizeOrNull(0f, Float.NEGATIVE_INFINITY, 1f))
    }

    @Test
    fun rejectsNearZeroVector() {
        assertNull(CalibrationPosePolicy.normalizeOrNull(0f, 0f, 0f))
        assertNull(CalibrationPosePolicy.normalizeOrNull(0.0001f, 0f, 0f))
    }

    @Test
    fun rejectsFiniteComponentsWhoseMagnitudeOverflowsFloat() {
        assertNull(CalibrationPosePolicy.normalizeOrNull(Float.MAX_VALUE, Float.MAX_VALUE, 0f))
    }

    @Test
    fun restoredPoseIsRenormalized() {
        val pose = CalibrationPosePolicy.normalizeOrNull(0f, 0f, 9.81f)

        requireNotNull(pose)
        assertTrue(abs(pose.z - 1f) < 0.0001f)
    }
}
