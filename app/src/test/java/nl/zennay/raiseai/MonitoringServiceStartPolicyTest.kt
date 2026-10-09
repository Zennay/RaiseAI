package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MonitoringServiceStartPolicyTest {
    @Test
    fun successfulServiceStartPasses() {
        assertTrue(MonitoringServiceStartPolicy.tryStart { true })
    }

    @Test
    fun missingServiceComponentFailsClosed() {
        assertFalse(MonitoringServiceStartPolicy.tryStart { false })
    }

    @Test
    fun securityFailureFailsClosed() {
        assertFalse(
            MonitoringServiceStartPolicy.tryStart {
                throw SecurityException("foreground service permission denied")
            }
        )
    }

    @Test
    fun foregroundStartStateFailureFailsClosed() {
        assertFalse(
            MonitoringServiceStartPolicy.tryStart {
                throw IllegalStateException("foreground service start not allowed")
            }
        )
    }

    @Test(expected = RuntimeException::class)
    fun unrelatedRuntimeFailureIsNotHidden() {
        MonitoringServiceStartPolicy.tryStart {
            throw RuntimeException("unexpected programming failure")
        }
    }
}
