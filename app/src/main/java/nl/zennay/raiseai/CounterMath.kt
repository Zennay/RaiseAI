package nl.zennay.raiseai

internal object CounterMath {
    fun addNonNegative(current: Long, delta: Long): Long {
        val safeCurrent = current.coerceAtLeast(0L)
        val safeDelta = delta.coerceAtLeast(0L)
        if (safeDelta > Long.MAX_VALUE - safeCurrent) return Long.MAX_VALUE
        return safeCurrent + safeDelta
    }

    fun incrementNonNegative(current: Int): Int {
        val safeCurrent = current.coerceAtLeast(0)
        return if (safeCurrent == Int.MAX_VALUE) Int.MAX_VALUE else safeCurrent + 1
    }
}
