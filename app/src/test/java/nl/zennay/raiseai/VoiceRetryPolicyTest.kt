package nl.zennay.raiseai

import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
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

    @Test
    fun concurrentConsumersCannotOverspendRetryBudget() {
        val policy = VoiceRetryPolicy(maxAutomaticRetries = 3)
        val start = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(8)

        try {
            val attempts = (1..32).map {
                pool.submit<Boolean> {
                    start.await()
                    policy.tryConsumeRetry()
                }
            }

            start.countDown()

            val successes = attempts.count { future ->
                future.get(2, TimeUnit.SECONDS)
            }

            assertEquals(3, successes)
            assertFalse(policy.tryConsumeRetry())
        } finally {
            pool.shutdownNow()
        }
    }

    @Test(expected = IllegalArgumentException::class)
    fun negativeRetryBudgetIsRejected() {
        VoiceRetryPolicy(maxAutomaticRetries = -1)
    }
}
