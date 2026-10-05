package nl.zennay.raiseai

import org.junit.Assert.assertEquals
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
}
