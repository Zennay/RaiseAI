package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class CounterMathTest {
    @Test
    fun sanitizesPersistedNegativeCountersOnRead() {
        assertEquals(0L, CounterMath.nonNegative(-1L))
        assertEquals(12L, CounterMath.nonNegative(12L))
        assertEquals(0, CounterMath.nonNegative(-1))
        assertEquals(12, CounterMath.nonNegative(12))
    }

    @Test
    fun addsNormalNonNegativeRuntimeCounters() {
        assertEquals(15L, CounterMath.addNonNegative(10L, 5L))
    }

    @Test
    fun rejectsNegativePersistedOrIncomingRuntimeCounters() {
        assertEquals(5L, CounterMath.addNonNegative(-10L, 5L))
        assertEquals(10L, CounterMath.addNonNegative(10L, -5L))
        assertEquals(0L, CounterMath.addNonNegative(-10L, -5L))
    }

    @Test
    fun saturatesRuntimeCounterOverflow() {
        assertEquals(
            Long.MAX_VALUE,
            CounterMath.addNonNegative(Long.MAX_VALUE - 2L, 3L)
        )
        assertEquals(
            Long.MAX_VALUE,
            CounterMath.addNonNegative(Long.MAX_VALUE, 1L)
        )
    }

    @Test
    fun triggerCountIncrementIsNonNegativeAndSaturating() {
        assertEquals(1, CounterMath.incrementNonNegative(0))
        assertEquals(1, CounterMath.incrementNonNegative(-7))
        assertEquals(Int.MAX_VALUE, CounterMath.incrementNonNegative(Int.MAX_VALUE))
    }
}
