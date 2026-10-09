package nl.zennay.raiseai

/**
 * Pure elapsed-time gate for repeated assistant launches.
 *
 * Callers must supply a monotonic clock (for example elapsedRealtime), not wall-clock time.
 * This policy does not launch assistants or modify gesture detection thresholds.
 */
internal object AssistantLaunchCooldownPolicy {
    const val DEFAULT_COOLDOWN_MS: Long = 1_500L

    /**
     * A missing previous launch permits the initial attempt.
     * Negative timestamps, clock rollback, and non-positive cooldown are rejected.
     * Subtraction only happens after ordering, avoiding overflow near Long.MAX_VALUE.
     */
    fun mayLaunch(
        nowElapsedMs: Long,
        previousLaunchElapsedMs: Long?,
        cooldownMs: Long = DEFAULT_COOLDOWN_MS
    ): Boolean = remainingMs(nowElapsedMs, previousLaunchElapsedMs, cooldownMs) == 0L

    /**
     * Returns the remaining monotonic cooldown, or null for invalid clock/policy data.
     * Null is deliberately not treated as ready, so callers fail closed.
     */
    fun remainingMs(
        nowElapsedMs: Long,
        previousLaunchElapsedMs: Long?,
        cooldownMs: Long = DEFAULT_COOLDOWN_MS
    ): Long? {
        if (nowElapsedMs < 0L || cooldownMs <= 0L) return null
        if (previousLaunchElapsedMs == null) return 0L
        if (previousLaunchElapsedMs < 0L || nowElapsedMs < previousLaunchElapsedMs) return null
        val elapsed = nowElapsedMs - previousLaunchElapsedMs
        return if (elapsed >= cooldownMs) 0L else cooldownMs - elapsed
    }
}
