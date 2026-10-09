package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceRecognitionSessionGateTest {
    @Test
    fun onlyNewestRecognizerGenerationIsAccepted() {
        val gate = VoiceRecognitionSessionGate()

        val first = gate.beginSession()
        val second = gate.beginSession()

        assertFalse(gate.accepts(first))
        assertTrue(gate.accepts(second))
    }

    @Test
    fun terminalCallbackInvalidatesCurrentGeneration() {
        val gate = VoiceRecognitionSessionGate()
        val current = gate.beginSession()

        gate.invalidate(current)

        assertFalse(gate.accepts(current))
    }

    @Test
    fun staleInvalidationCannotCancelReplacementRecognizer() {
        val gate = VoiceRecognitionSessionGate()
        val stale = gate.beginSession()
        val current = gate.beginSession()

        gate.invalidate(stale)

        assertTrue(gate.accepts(current))
    }

    @Test
    fun invalidateAllRejectsPreviouslyCurrentRecognizer() {
        val gate = VoiceRecognitionSessionGate()
        val current = gate.beginSession()

        gate.invalidateAll()

        assertFalse(gate.accepts(current))
    }
}
