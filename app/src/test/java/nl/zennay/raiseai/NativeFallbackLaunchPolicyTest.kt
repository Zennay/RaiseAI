package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class NativeFallbackLaunchPolicyTest {
    @Test
    fun successfulFallbackFinishesNativeVoice() {
        assertEquals(
            NativeFallbackLaunchAction.FINISH_NATIVE_VOICE,
            NativeFallbackLaunchPolicy.actionFor(launchSucceeded = true)
        )
    }

    @Test
    fun failedFallbackKeepsRecoveryUiVisible() {
        assertEquals(
            NativeFallbackLaunchAction.KEEP_RECOVERY_UI,
            NativeFallbackLaunchPolicy.actionFor(launchSucceeded = false)
        )
    }
}
