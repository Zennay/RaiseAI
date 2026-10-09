package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class AssistantModeStoreTest {
    @Test
    fun missingPreferenceDefaultsToGemini() {
        assertEquals(AssistantMode.GEMINI, AssistantModeStore.resolve(null))
    }

    @Test
    fun unknownPreferenceFailsClosedToGemini() {
        assertEquals(AssistantMode.GEMINI, AssistantModeStore.resolve("unexpected"))
    }

    @Test
    fun explicitGeminiPreferenceUsesGemini() {
        assertEquals(AssistantMode.GEMINI, AssistantModeStore.resolve(AssistantMode.GEMINI.storedValue))
    }

    @Test
    fun explicitNativePreferenceUsesNativeRaiseAi() {
        assertEquals(AssistantMode.NATIVE, AssistantModeStore.resolve(AssistantMode.NATIVE.storedValue))
    }

    @Test
    fun assistantModesExposeTheOtherModeAsAlternate() {
        assertEquals(AssistantMode.NATIVE, AssistantMode.GEMINI.alternate())
        assertEquals(AssistantMode.GEMINI, AssistantMode.NATIVE.alternate())
    }

    @Test
    fun unreadablePreferenceFailsSafeToMissingValue() {
        val stored = AssistantModeStore.readStoredValue {
            throw IllegalStateException("preferences unavailable")
        }

        assertEquals(null, stored)
        assertEquals(AssistantMode.GEMINI, AssistantModeStore.resolve(stored))
    }

    @Test
    fun wrongTypedPreferenceFailsSafeToMissingValue() {
        val stored = AssistantModeStore.readStoredValue {
            throw ClassCastException("assistant_mode is not a string")
        }

        assertEquals(null, stored)
        assertEquals(AssistantMode.GEMINI, AssistantModeStore.resolve(stored))
    }

    @Test
    fun fatalErrorsStillPropagate() {
        try {
            AssistantModeStore.readStoredValue {
                throw AssertionError("fatal")
            }
            fail("Expected fatal Error to propagate")
        } catch (_: AssertionError) {
            // Expected: only recoverable runtime preference failures are contained.
        }
    }
}
