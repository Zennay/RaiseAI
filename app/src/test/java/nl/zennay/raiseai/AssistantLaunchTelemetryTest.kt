package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class AssistantLaunchTelemetryTest {
    @Test
    fun successfulTelemetryWriteRunsNormally() {
        var writes = 0

        AssistantLaunchTelemetry.record { writes += 1 }

        assertEquals(1, writes)
    }

    @Test
    fun runtimeTelemetryFailureDoesNotEscape() {
        var attempts = 0

        AssistantLaunchTelemetry.record {
            attempts += 1
            throw IllegalStateException("prefs unavailable")
        }

        assertEquals(1, attempts)
    }

    @Test(expected = AssertionError::class)
    fun fatalErrorsAreNotSwallowed() {
        AssistantLaunchTelemetry.record {
            throw AssertionError("fatal")
        }
    }
}
