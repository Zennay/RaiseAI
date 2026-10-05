package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class RaiseTargetTest {
    @Test
    fun missingPreferenceDefaultsToGemini() {
        assertEquals(RaiseTarget.GEMINI, RaiseTarget.fromStored(null))
        assertEquals(RaiseTarget.GEMINI, RaiseTarget.fromStored(""))
        assertEquals(RaiseTarget.GEMINI, RaiseTarget.fromStored("unknown"))
    }

    @Test
    fun storedTargetsRoundTrip() {
        assertEquals(RaiseTarget.GEMINI, RaiseTarget.fromStored("gemini"))
        assertEquals(RaiseTarget.NATIVE, RaiseTarget.fromStored("native"))
    }
}
