package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeMicLevelScalePolicyTest {
    @Test fun nonFiniteLevelsResetOrbToNeutralScale() {
        listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY)
            .forEach { assertEquals(1f, NativeMicLevelScalePolicy.scale(it), 0f) }
    }

    @Test fun negativeAndZeroDecibelsDoNotShrinkOrb() {
        listOf(-1000f, -10f, -0f, 0f).forEach {
            assertEquals(1f, NativeMicLevelScalePolicy.scale(it), 0f)
        }
    }

    @Test fun largePositiveLevelsNeverGrowOrbBeyondBoundedMaximum() {
        val maximum = 1f + 10f / 45f
        listOf(10f, 11f, 1_000_000f, Float.MAX_VALUE).forEach {
            assertEquals(maximum, NativeMicLevelScalePolicy.scale(it), 0.000001f)
        }
    }

    @Test fun normalLevelsPreserveExistingOrbResponse() {
        for (rms in listOf(0.5f, 1f, 3.4f, 5f, 9.9f)) {
            assertEquals(1f + rms / 45f, NativeMicLevelScalePolicy.scale(rms), 0.000001f)
        }
    }

    @Test fun allEmittedScalesAreFiniteAndBounded() {
        val values = listOf(
            Float.NaN, Float.NEGATIVE_INFINITY, Float.POSITIVE_INFINITY,
            -Float.MAX_VALUE, -1f, 0f, Float.MIN_VALUE, 0.75f, 10f,
            Float.MAX_VALUE
        )
        for (value in values) {
            val scale = NativeMicLevelScalePolicy.scale(value)
            assertTrue("invalid scale for $value: $scale", scale.isFinite())
            assertTrue("scale too small for $value: $scale", scale >= 1f)
            assertTrue("scale too large for $value: $scale", scale <= 1f + 10f / 45f)
        }
    }
}
