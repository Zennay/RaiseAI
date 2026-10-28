package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class VoiceErrorRecoveryPolicyTest {
    @Test
    fun emptySpeechCanRetrySubjectToSeparateBoundedBudget() {
        assertEquals(
            VoiceErrorRecoveryPolicy.Recovery.RETRY_IF_BUDGET_AVAILABLE,
            VoiceErrorRecoveryPolicy.decide(VoiceErrorRecoveryPolicy.Failure.NO_MATCH)
        )
        assertEquals(
            VoiceErrorRecoveryPolicy.Recovery.RETRY_IF_BUDGET_AVAILABLE,
            VoiceErrorRecoveryPolicy.decide(VoiceErrorRecoveryPolicy.Failure.SPEECH_TIMEOUT)
        )
    }

    @Test
    fun infrastructureAndPermissionFailuresNeverAutomaticallyRetry() {
        listOf(
            VoiceErrorRecoveryPolicy.Failure.PERMISSION_DENIED,
            VoiceErrorRecoveryPolicy.Failure.NETWORK,
            VoiceErrorRecoveryPolicy.Failure.RECOGNIZER_UNAVAILABLE,
            VoiceErrorRecoveryPolicy.Failure.OTHER
        ).forEach { failure ->
            assertEquals(
                "Unsafe automatic retry for $failure",
                VoiceErrorRecoveryPolicy.Recovery.REQUIRE_USER_ACTION,
                VoiceErrorRecoveryPolicy.decide(failure)
            )
        }
    }

    @Test
    fun allFailuresHaveAnExplicitRecoveryDecision() {
        assertEquals(
            VoiceErrorRecoveryPolicy.Failure.values().size,
            VoiceErrorRecoveryPolicy.Failure.values().count {
                VoiceErrorRecoveryPolicy.decide(it) in VoiceErrorRecoveryPolicy.Recovery.values()
            }
        )
    }
}
