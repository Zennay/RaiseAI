package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import kotlin.math.sqrt

class MouthPoseTest {
    @Test
    fun normalizesFiniteVector() {
        val pose = MouthPose.normalizedOrNull(1f, 2f, 3f)

        assertNotNull(pose)
        val value = requireNotNull(pose)
        val length = sqrt(value.x * value.x + value.y * value.y + value.z * value.z)
        assertEquals(1f, length, 0.0001f)
    }

    @Test
    fun rejectsNonFiniteVectors() {
        assertNull(MouthPose.normalizedOrNull(Float.NaN, 1f, 2f))
        assertNull(MouthPose.normalizedOrNull(1f, Float.POSITIVE_INFINITY, 2f))
        assertNull(MouthPose.normalizedOrNull(1f, 2f, Float.NEGATIVE_INFINITY))
    }

    @Test
    fun rejectsZeroAndNearZeroVectors() {
        assertNull(MouthPose.normalizedOrNull(0f, 0f, 0f))
        assertNull(MouthPose.normalizedOrNull(0.0001f, 0f, 0f))
    }

    @Test
    fun rejectsMagnitudeOverflow() {
        assertNull(MouthPose.normalizedOrNull(Float.MAX_VALUE, Float.MAX_VALUE, Float.MAX_VALUE))
    }
}
