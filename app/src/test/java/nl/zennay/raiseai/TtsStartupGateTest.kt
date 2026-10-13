package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TtsStartupGateTest {
    @Test fun initializationSuccessAllowsSpeechAndPreventsDuplicateInitialization() {
        val gate = TtsStartupGate()
        val ticket = gate.begin()
        assertNotNull(ticket)
        assertNull(gate.begin())
        assertTrue(gate.complete(requireNotNull(ticket), true))
        assertTrue(gate.isReady())
        assertNull(gate.begin())
    }

    @Test fun initializationFailureAllowsExplicitRetry() {
        val gate = TtsStartupGate()
        val first = requireNotNull(gate.begin())
        assertTrue(gate.complete(first, false))
        assertFalse(gate.isReady())
        val second = requireNotNull(gate.begin())
        assertFalse(first == second)
        assertFalse(gate.complete(first, true))
        assertTrue(gate.complete(second, true))
        assertTrue(gate.isReady())
    }

    @Test fun missingLanguageCanBeReportedAsInitializationFailureAndRetried() {
        val gate = TtsStartupGate()
        assertTrue(gate.complete(requireNotNull(gate.begin()), false))
        assertNotNull(gate.begin())
    }

    @Test fun closeInvalidatesDelayedCallbacksAndPreventsReopening() {
        val gate = TtsStartupGate()
        val ticket = requireNotNull(gate.begin())
        gate.close()
        assertFalse(gate.complete(ticket, true))
        assertFalse(gate.isReady())
        assertNull(gate.begin())
    }

    @Test fun neverAcceptsUnsolicitedCallbacks() {
        val gate = TtsStartupGate()
        assertFalse(gate.complete(1, true))
        val ticket = requireNotNull(gate.begin())
        assertFalse(gate.complete(ticket + 1, true))
        assertTrue(gate.complete(ticket, true))
    }
}
