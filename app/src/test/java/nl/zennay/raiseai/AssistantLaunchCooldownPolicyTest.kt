package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantLaunchCooldownPolicyTest {
    @Test fun firstLaunchIsAllowed() {
        assertTrue(AssistantLaunchCooldownPolicy.mayLaunch(0L, null))
    }

    @Test fun blocksUntilCooldownBoundary() {
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(1_499L, 0L))
        assertTrue(AssistantLaunchCooldownPolicy.mayLaunch(1_500L, 0L))
    }

    @Test fun rejectsClockRollbackAndInvalidElapsedTime() {
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(10L, 11L))
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(-1L, null))
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(100L, -1L))
    }

    @Test fun rejectsNonPositiveCooldown() {
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(100L, null, 0L))
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(100L, 0L, -1L))
    }

    @Test fun handlesLargeMonotonicValuesWithoutAddingDeadlines() {
        assertFalse(AssistantLaunchCooldownPolicy.mayLaunch(Long.MAX_VALUE, Long.MAX_VALUE - 1L, 2L))
        assertTrue(AssistantLaunchCooldownPolicy.mayLaunch(Long.MAX_VALUE, Long.MAX_VALUE - 2L, 2L))
    }
}
