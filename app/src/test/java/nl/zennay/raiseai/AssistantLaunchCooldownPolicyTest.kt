package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantLaunchCooldownPolicyTest {
    @Test fun firstLaunchIsAllowed() {
        assertTrue(AssistantLaunchCooldownPolicy.mayLaunch(0L, null))
        assertEquals(0L, AssistantLaunchCooldownPolicy.remainingMs(0L, null))
    }

    @Test fun blocksUntilCooldownBoundary() {
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(1_499L, 0L))
        assertTrue(AssistantLaunchCooldownPolicy.mayLaunch(1_500L, 0L))
        assertEquals(1L, AssistantLaunchCooldownPolicy.remainingMs(1_499L, 0L))
        assertEquals(0L, AssistantLaunchCooldownPolicy.remainingMs(1_500L, 0L))
    }

    @Test fun reportsRemainingDurationWithoutOverflow() {
        assertEquals(1_500L, AssistantLaunchCooldownPolicy.remainingMs(50L, 50L))
        assertEquals(500L, AssistantLaunchCooldownPolicy.remainingMs(1_050L, 50L))
        assertEquals(0L, AssistantLaunchCooldownPolicy.remainingMs(1_551L, 50L))
    }

    @Test fun rejectsClockRollbackAndInvalidElapsedTime() {
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(10L, 11L))
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(-1L, null))
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(100L, -1L))
        assertNull(AssistantLaunchCooldownPolicy.remainingMs(10L, 11L))
        assertNull(AssistantLaunchCooldownPolicy.remainingMs(-1L, null))
    }

    @Test fun rejectsNonPositiveCooldown() {
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(100L, null, 0L))
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(100L, 0L, -1L))
        assertNull(AssistantLaunchCooldownPolicy.remainingMs(100L, null, 0L))
    }

    @Test fun handlesLargeMonotonicValuesWithoutAddingDeadlines() {
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(Long.MAX_VALUE, Long.MAX_VALUE - 1L, 2L))
        assertTrue(AssistantLaunchCooldownPolicy.mayLaunch(Long.MAX_VALUE, Long.MAX_VALUE - 2L, 2L))
        assertEquals(1L, AssistantLaunchCooldownPolicy.remainingMs(Long.MAX_VALUE, Long.MAX_VALUE - 1L, 2L))
    }
}
