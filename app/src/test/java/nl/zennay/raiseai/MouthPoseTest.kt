package nl.zennay.raiseai

import kotlin.math.sqrt
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class MouthPoseTest {
    @Test
    fun normalizesFiniteScaledPose() {
        val normalized = MouthPose(3f, 4f, 0f).normalizedOrNull()

        assertNotNull(normalized)
        assertEquals(0.6f, normalized!!.x, 0.000001f)
        assertEquals(0.8f, normalized.y, 0.000001f)
        assertEquals(0f, normalized.z, 0.000001f)
    }

    @Test
    fun keepsHugeFiniteComponentsNumericallyUsable() {
        val normalized = MouthPose(Float.MAX_VALUE, Float.MAX_VALUE / 2f, 0f).normalizedOrNull()

        assertNotNull(normalized)
        val length = sqrt(
            normalized!!.x.toDouble() * normalized.x +
                normalized.y.toDouble() * normalized.y +
                normalized.z.toDouble() * normalized.z
        )
        assertEquals(1.0, length, 0.000001)
    }

    @Test
    fun rejectsNonFiniteComponents() {
        assertNull(MouthPose(Float.NaN, 0f, 1f).normalizedOrNull())
        assertNull(MouthPose(Float.POSITIVE_INFINITY, 0f, 1f).normalizedOrNull())
        assertNull(MouthPose(0f, Float.NEGATIVE_INFINITY, 1f).normalizedOrNull())
    }

    @Test
    fun rejectsDegeneratePose() {
        assertNull(MouthPose(0f, 0f, 0f).normalizedOrNull())
        assertNull(MouthPose(0.0001f, 0f, 0f).normalizedOrNull())
    }

    @Test
    fun acceptsMinimumUsableMagnitude() {
        val normalized = MouthPose(0.001f, 0f, 0f).normalizedOrNull()

        assertNotNull(normalized)
        assertEquals(1f, normalized!!.x, 0f)
        assertEquals(0f, normalized.y, 0f)
        assertEquals(0f, normalized.z, 0f)
    }
}
