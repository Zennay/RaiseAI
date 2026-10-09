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
    ): Boolean {
        if (nowElapsedMs < 0L || cooldownMs <= 0L) return false
        if (previousLaunchElapsedMs == null) return true
        if (previousLaunchElapsedMs < 0L || nowElapsedMs < previousLaunchElapsedMs) return false
        return nowElapsedMs - previousLaunchElapsedMs >= cooldownMs
    }
}
