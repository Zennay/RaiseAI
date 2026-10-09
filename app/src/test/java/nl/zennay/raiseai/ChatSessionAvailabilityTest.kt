package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatSessionAvailabilityTest {
    @Test
    fun navigationStartKeepsInitialLoadRequiredUntilSuccess() {
        val state = ChatSessionAvailability()

        state.markNavigationStarted()

        assertTrue(state.needsInitialLoad)
        state.markPageAvailable()
        assertFalse(state.needsInitialLoad)
    }


    @Test
    fun newNavigationMakesPreviouslyAvailablePageRequireRetryUntilSuccess() {
        val state = ChatSessionAvailability()
        state.markPageAvailable()
        assertFalse(state.needsInitialLoad)

        state.markNavigationStarted()

        assertTrue(state.needsInitialLoad)
        state.markPageAvailable()
        assertFalse(state.needsInitialLoad)
    }

    @Test
    fun failedLoadRequiresRetryAfterPreviouslyAvailablePage() {
        val state = ChatSessionAvailability()
        state.markPageAvailable()

        state.markLoadFailed()

        assertTrue(state.needsInitialLoad)
    }

    @Test
    fun resetRequiresInitialLoadAgain() {
        val state = ChatSessionAvailability()
        state.markPageAvailable()

        state.reset()

        assertTrue(state.needsInitialLoad)
    }
}
