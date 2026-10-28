package nl.zennay.raiseai

/**
 * Pure decision policy for recognition failures. The caller maps Android recognizer
 * errors into these categories; no platform dependency or UI side effect lives here.
 *
 * Only missing speech is eligible for an automatic retry. Permission, network and
 * service failures require an explicit user action rather than a retry loop.
 */
internal object VoiceErrorRecoveryPolicy {
    enum class Failure {
        NO_MATCH,
        SPEECH_TIMEOUT,
        PERMISSION_DENIED,
        NETWORK,
        RECOGNIZER_UNAVAILABLE,
        OTHER
    }

    enum class Recovery {
        RETRY_IF_BUDGET_AVAILABLE,
        REQUIRE_USER_ACTION
    }

    fun decide(failure: Failure): Recovery = when (failure) {
        Failure.NO_MATCH,
        Failure.SPEECH_TIMEOUT -> Recovery.RETRY_IF_BUDGET_AVAILABLE
        Failure.PERMISSION_DENIED,
        Failure.NETWORK,
        Failure.RECOGNIZER_UNAVAILABLE,
        Failure.OTHER -> Recovery.REQUIRE_USER_ACTION
    }
}
