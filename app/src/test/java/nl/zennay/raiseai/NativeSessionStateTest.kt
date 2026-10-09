package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeSessionStateTest {
    @Test
    fun idleIsTheOnlyStateThatAllowsAnotherGesture() {
        assertFalse(NativeSessionState.blocksGesture("idle"))
    }

    @Test
    fun knownActiveStatesBlockAnotherGesture() {
        listOf(
            "starting",
            "listening",
            "understanding",
            "sending",
            "executing",
            "replying"
        ).forEach { state ->
            assertTrue("expected $state to block another gesture", NativeSessionState.blocksGesture(state))
        }
    }

    @Test
    fun reviewAndErrorStatesFailClosed() {
        listOf("reviewing", "error").forEach { state ->
            assertTrue("expected $state to block another gesture", NativeSessionState.blocksGesture(state))
        }
    }

    @Test
    fun unknownOrMalformedStatesFailClosed() {
        listOf("", "unexpected", "READY").forEach { state ->
            assertTrue("expected '$state' to block another gesture", NativeSessionState.blocksGesture(state))
        }
    }
}
