package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ForegroundActivityStateTest {
    @Test
    fun resumedPackageIsCurrent() {
        assertEquals(
            "com.google.assistant",
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition("com.google.assistant", 100L, resumed = true)
                )
            )
        )
    }

    @Test
    fun pausedCurrentPackageClearsForegroundState() {
        assertNull(
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition("com.google.assistant", 100L, resumed = true),
                    ForegroundTransition("com.google.assistant", 200L, resumed = false)
                )
            )
        )
    }

    @Test
    fun backgroundEventForOlderPackageDoesNotClearNewForegroundApp() {
        assertEquals(
            "nl.zennay.raiseai",
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition("com.google.assistant", 100L, resumed = true),
                    ForegroundTransition("nl.zennay.raiseai", 200L, resumed = true),
                    ForegroundTransition("com.google.assistant", 300L, resumed = false)
                )
            )
        )
    }

    @Test
    fun laterResumedPackageWins() {
        assertEquals(
            "nl.zennay.raiseai",
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition("com.google.assistant", 100L, resumed = true),
                    ForegroundTransition("nl.zennay.raiseai", 300L, resumed = true)
                )
            )
        )
    }

    @Test
    fun timestampsAreProcessedChronologicallyWithStableTieOrder() {
        assertNull(
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition("com.google.assistant", 200L, resumed = false),
                    ForegroundTransition("com.google.assistant", 100L, resumed = true)
                )
            )
        )

        assertNull(
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition("com.google.assistant", 100L, resumed = true),
                    ForegroundTransition("com.google.assistant", 100L, resumed = false)
                )
            )
        )
    }
}
