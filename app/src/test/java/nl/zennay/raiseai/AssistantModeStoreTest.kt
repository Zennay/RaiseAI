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
    fun explicitChatGptPreferenceUsesChatGpt() {
        assertEquals(AssistantMode.CHATGPT, AssistantModeStore.resolve(AssistantMode.CHATGPT.storedValue))
    }

    @Test
    fun legacyPreferenceSchemaMigratesBackToGemini() {
        assertEquals(
            AssistantMode.GEMINI,
            AssistantModeStore.resolve(AssistantMode.NATIVE.storedValue, AssistantModeStore.CURRENT_MODE_SCHEMA - 1)
        )
    }

    @Test
    fun currentPreferenceSchemaKeepsUserSelection() {
        assertEquals(
            AssistantMode.CHATGPT,
            AssistantModeStore.resolve(AssistantMode.CHATGPT.storedValue, AssistantModeStore.CURRENT_MODE_SCHEMA)
        )
    }

    @Test
    fun assistantModesCycleThroughAllAvailableChoices() {
        assertEquals(AssistantMode.NATIVE, AssistantMode.GEMINI.next())
        assertEquals(AssistantMode.CHATGPT, AssistantMode.NATIVE.next())
        assertEquals(AssistantMode.GEMINI, AssistantMode.CHATGPT.next())
    }
}
