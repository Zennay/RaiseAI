package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class HapticFeedbackPolicyTest {
    @Test
    fun successfulFeedbackReturnsTrue() {
        var invoked = false

        val result = HapticFeedbackPolicy.run {
            invoked = true
        }

        assertTrue(invoked)
        assertTrue(result)
    }

    @Test
    fun runtimeFailureReturnsFalse() {
        val result = HapticFeedbackPolicy.run {
            throw IllegalStateException("vibrator unavailable")
        }

        assertFalse(result)
    }

    @Test
    fun fatalErrorsStillPropagate() {
        val fatal = FatalTestError()

        try {
            HapticFeedbackPolicy.run { throw fatal }
            fail("Expected fatal error to propagate")
        } catch (error: FatalTestError) {
            assertSame(fatal, error)
        }
    }

    private class FatalTestError : Error()
}
