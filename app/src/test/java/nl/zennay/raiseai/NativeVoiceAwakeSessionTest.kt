package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeVoiceAwakeSessionTest {
    private val budget = NativeVoiceScreenAwakePolicy.MAX_INTERACTIVE_AWAKE_MS

    @Test fun sessionWithoutExplicitStartNeverKeepsDisplayAwake() {
        val session = NativeVoiceAwakeSession()
        assertEquals(0L, session.remainingMs("listening", 1_000L))
        assertFalse(session.shouldKeepScreenAwake("listening", 1_000L))
    }

    @Test fun sessionStartsWithFullBudget() {
        val session = NativeVoiceAwakeSession()
        assertTrue(session.startIfAbsent(50_000L))
        assertEquals(budget, session.remainingMs("starting", 50_000L))
        assertTrue(session.shouldKeepScreenAwake("listening", 50_001L))
    }

    @Test fun automaticRetriesCannotResetDeadline() {
        val session = NativeVoiceAwakeSession()
        assertTrue(session.startIfAbsent(1_000L))
        assertFalse(session.startIfAbsent(10_000L))
        assertEquals(1L, session.remainingMs("listening", 1_000L + budget - 1L))
        assertFalse(session.startIfAbsent(1_000L + budget))
        assertEquals(0L, session.remainingMs("listening", 1_000L + budget))
    }

    @Test fun duplicateReadyAndUiRebindCallsCannotExtendWindow() {
        val session = NativeVoiceAwakeSession()
        assertTrue(session.startIfAbsent(100L))
        repeat(50) { assertFalse(session.startIfAbsent(100L + it * 100L)) }
        assertEquals(0L, session.remainingMs("understanding", 100L + budget))
    }

    @Test fun terminalSendAndReplyStatesReleaseDisplayHold() {
        val session = NativeVoiceAwakeSession()
        session.startIfAbsent(0L)
        assertEquals(0L, session.remainingMs("sending", 1L))
        assertEquals(0L, session.remainingMs("replying", 2L))
        assertEquals(0L, session.remainingMs("error", 3L))
    }

    @Test fun explicitFinishAllowsOneNewIndependentSession() {
        val session = NativeVoiceAwakeSession()
        assertTrue(session.startIfAbsent(0L))
        assertEquals(0L, session.remainingMs("listening", budget))
        session.finish()
        assertEquals(0L, session.remainingMs("listening", budget))
        assertTrue(session.startIfAbsent(budget + 1L))
        assertEquals(budget, session.remainingMs("listening", budget + 1L))
    }

    @Test fun invalidStartMustNotConsumeOrAuthorizeSession() {
        val session = NativeVoiceAwakeSession()
        assertFalse(session.startIfAbsent(-1L))
        assertEquals(0L, session.remainingMs("starting", 0L))
        assertTrue(session.startIfAbsent(0L))
        assertEquals(budget, session.remainingMs("starting", 0L))
    }

    @Test fun futureOrRollbackTimeFailsClosed() {
        val session = NativeVoiceAwakeSession()
        session.startIfAbsent(5_000L)
        assertEquals(0L, session.remainingMs("listening", 4_999L))
        assertEquals(0L, session.remainingMs("listening", -1L))
    }

    @Test fun monotonicLargeValuesRemainBounded() {
        val session = NativeVoiceAwakeSession()
        assertTrue(session.startIfAbsent(Long.MAX_VALUE - 1L))
        assertEquals(budget - 1L, session.remainingMs("listening", Long.MAX_VALUE))
    }

    @Test fun finishedSessionDoesNotResumeOnStaleCallback() {
        val session = NativeVoiceAwakeSession()
        session.startIfAbsent(1L)
        session.finish()
        assertFalse(session.shouldKeepScreenAwake("listening", 2L))
        assertEquals(0L, session.remainingMs("understanding", 2L))
    }
}
