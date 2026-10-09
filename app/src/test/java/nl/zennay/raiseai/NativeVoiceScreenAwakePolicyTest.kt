package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeVoiceScreenAwakePolicyTest {
    private fun awake(
        state: String?,
        now: Long = 5_000L,
        started: Long = 1_000L
    ) = NativeVoiceScreenAwakePolicy.shouldKeepScreenAwake(state, now, started)

    private fun remaining(
        state: String?,
        now: Long,
        started: Long
    ) = NativeVoiceScreenAwakePolicy.remainingAwakeMs(state, now, started)

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

    @Test fun deadlineDelayMatchesRemainingInteractiveBudget() {
        val max = NativeVoiceScreenAwakePolicy.MAX_INTERACTIVE_AWAKE_MS
        assertEquals(max, remaining("starting", now = 0L, started = 0L))
        assertEquals(500L, remaining("listening", now = max - 500L, started = 0L))
        assertEquals(1L, remaining("understanding", now = max - 1L, started = 0L))
        assertEquals(0L, remaining("listening", now = max, started = 0L))
    }

    @Test fun nonInteractiveStatesNeverScheduleExpiry() {
        assertEquals(0L, remaining("sending", now = 1L, started = 0L))
        assertEquals(0L, remaining("replying", now = 1L, started = 0L))
        assertEquals(0L, remaining("error", now = 1L, started = 0L))
        assertEquals(0L, remaining(null, now = 1L, started = 0L))
    }

    @Test fun invalidElapsedTimeNeverSchedulesExpiry() {
        assertEquals(0L, remaining("listening", now = 4L, started = 5L))
        assertEquals(0L, remaining("listening", now = -1L, started = 0L))
        assertEquals(0L, remaining("listening", now = 0L, started = -1L))
    }

    @Test fun hugeMonotonicOriginsDoNotOverflowDeadline() {
        assertEquals(1L, remaining("listening", now = Long.MAX_VALUE, started = Long.MAX_VALUE - (NativeVoiceScreenAwakePolicy.MAX_INTERACTIVE_AWAKE_MS - 1L)))
        assertEquals(0L, remaining("listening", now = Long.MAX_VALUE, started = 0L))
    }
}
