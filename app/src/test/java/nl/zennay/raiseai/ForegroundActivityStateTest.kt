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
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        activityName = "AssistantActivity"
                    )
                )
            )
        )
    }

    @Test
    fun pausedCurrentActivityClearsForegroundState() {
        assertNull(
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        activityName = "AssistantActivity"
                    ),
                    ForegroundTransition(
                        "com.google.assistant",
                        200L,
                        resumed = false,
                        activityName = "AssistantActivity"
                    )
                )
            )
        )
    }

    @Test
    fun pausingOneActivityDoesNotClearAnotherResumedActivityInSamePackage() {
        assertEquals(
            "com.google.assistant",
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        activityName = "AssistantActivity"
                    ),
                    ForegroundTransition(
                        "com.google.assistant",
                        200L,
                        resumed = true,
                        activityName = "ConversationActivity"
                    ),
                    ForegroundTransition(
                        "com.google.assistant",
                        300L,
                        resumed = false,
                        activityName = "AssistantActivity"
                    )
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
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        activityName = "AssistantActivity"
                    ),
                    ForegroundTransition(
                        "nl.zennay.raiseai",
                        200L,
                        resumed = true,
                        activityName = "MainActivity"
                    ),
                    ForegroundTransition(
                        "com.google.assistant",
                        300L,
                        resumed = false,
                        activityName = "AssistantActivity"
                    )
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
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        activityName = "AssistantActivity"
                    ),
                    ForegroundTransition(
                        "nl.zennay.raiseai",
                        300L,
                        resumed = true,
                        activityName = "MainActivity"
                    )
                )
            )
        )
    }

    @Test
    fun packageWideBackgroundClearsLegacyForegroundState() {
        assertNull(
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        packageWide = true
                    ),
                    ForegroundTransition(
                        "com.google.assistant",
                        200L,
                        resumed = false,
                        packageWide = true
                    )
                )
            )
        )
    }

    @Test
    fun unidentifiedActivityBackgroundDoesNotProveWholePackageLeftForeground() {
        assertEquals(
            "com.google.assistant",
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        activityName = "AssistantActivity"
                    ),
                    ForegroundTransition(
                        "com.google.assistant",
                        200L,
                        resumed = false
                    )
                )
            )
        )
    }

    @Test
    fun timestampsAreProcessedChronologicallyWithStableTieOrder() {
        assertNull(
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition(
                        "com.google.assistant",
                        200L,
                        resumed = false,
                        activityName = "AssistantActivity"
                    ),
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        activityName = "AssistantActivity"
                    )
                )
            )
        )

        assertNull(
            ForegroundActivityState.currentPackage(
                sequenceOf(
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = true,
                        activityName = "AssistantActivity"
                    ),
                    ForegroundTransition(
                        "com.google.assistant",
                        100L,
                        resumed = false,
                        activityName = "AssistantActivity"
                    )
                )
            )
        )
    }
}
