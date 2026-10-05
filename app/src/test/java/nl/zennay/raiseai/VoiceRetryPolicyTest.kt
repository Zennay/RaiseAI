package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceRetryPolicyTest {
    @Test
    fun allowsOnlyConfiguredNumberOfAutomaticRetries() {
        val policy = VoiceRetryPolicy(maxAutomaticRetries = 1)

        assertTrue(policy.tryConsumeRetry())
        assertFalse(policy.tryConsumeRetry())
        assertFalse(policy.tryConsumeRetry())
    }

    @Test
    fun zeroRetryBudgetFailsClosed() {
        val policy = VoiceRetryPolicy(maxAutomaticRetries = 0)

        assertFalse(policy.tryConsumeRetry())
    }

    @Test(expected = IllegalArgumentException::class)
    fun negativeRetryBudgetIsRejected() {
        VoiceRetryPolicy(maxAutomaticRetries = -1)
    }
}
