package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeVoiceScreenAwakePolicyTest {
    private fun awake(
        state: String?,
        now: Long = 5_000L,
        started: Long = 1_000L
    ) = NativeVoiceScreenAwakePolicy.shouldKeepScreenAwake(state, now, started)

    @Test fun preparingForSpeechMayKeepDisplayAwake() {
        assertTrue(awake("starting"))
    }

    @Test fun interactiveListeningMayKeepDisplayAwake() {
        assertTrue(awake("listening"))
    }

    @Test fun recognizerFinalizingSpeechMayKeepDisplayAwake() {
        assertTrue(awake("understanding"))
    }

    @Test fun networkSendDoesNotHoldScreenAwake() {
        assertFalse(awake("sending"))
    }

    @Test fun responseDisplayDoesNotHoldScreenAwake() {
        assertFalse(awake("replying"))
    }

    @Test fun backgroundExecutionDoesNotHoldScreenAwake() {
        assertFalse(awake("executing"))
    }

    @Test fun terminalErrorNeverHoldsScreenAwake() {
        assertFalse(awake("error"))
    }

    @Test fun unknownOrMissingStateFailsClosed() {
        assertFalse(awake("LISTENING"))
        assertFalse(awake("unknown"))
        assertFalse(awake(null))
    }

    @Test fun exactBudgetIsNoLongerAllowed() {
        val limit = NativeVoiceScreenAwakePolicy.MAX_INTERACTIVE_AWAKE_MS
        assertTrue(awake("listening", now = limit - 1L, started = 0L))
        assertFalse(awake("listening", now = limit, started = 0L))
        assertFalse(awake("listening", now = limit + 1L, started = 0L))
    }

    @Test fun freshSessionGetsIndependentBudget() {
        assertTrue(awake("listening", now = 500_000L, started = 499_999L))
        assertFalse(awake("listening", now = 500_000L, started = 400_000L))
    }

    @Test fun clockRollbackFailsClosedInsteadOfExtendingWindow() {
        assertFalse(awake("listening", now = 99L, started = 100L))
    }

    @Test fun negativeTimestampInputsFailClosed() {
        assertFalse(awake("listening", now = -1L, started = 0L))
        assertFalse(awake("listening", now = 0L, started = -1L))
    }

    @Test fun nearMaxLongTimestampsDoNotOverflow() {
        assertTrue(awake("listening", now = Long.MAX_VALUE, started = Long.MAX_VALUE - 1L))
        assertFalse(awake("listening", now = Long.MAX_VALUE, started = 0L))
    }

    @Test fun idleScreenShouldNeverStayAwake() {
        assertFalse(awake("idle", now = 0L, started = 0L))
    }
}
