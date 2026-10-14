package nl.zennay.raiseai

/**
 * Rejects accelerometer events that cannot safely advance one continuous gesture stream.
 *
 * Android sensor event timestamps and SystemClock.elapsedRealtimeNanos() share the same
 * elapsed-realtime timebase. Each registered sensor stream owns one instance of this policy.
 * Call [reset] after unregistering the listener; a fresh registration must not inherit the
 * timestamp of an earlier stream.
 *
 * This is a pure policy for the GestureMonitorService owner to wire into the runtime.
 * It deliberately does not normalize vectors or change gesture thresholds.
 */
internal class AccelerometerEventOrderPolicy {
    private var lastAcceptedTimestampNs = 0L

    fun accept(values: FloatArray?, timestampNs: Long, nowElapsedRealtimeNs: Long): Boolean {
        if (values == null || values.size < 3) return false
        if (!values[0].isFinite() || !values[1].isFinite() || !values[2].isFinite()) {
            return false
        }
        if (timestampNs <= 0L || nowElapsedRealtimeNs <= 0L) return false

        // Strict monotonicity prevents replay and out-of-order batches from rewinding detector
        // windows. Invalid observations never consume a sequence slot.
        if (timestampNs <= lastAcceptedTimestampNs) return false

        if (timestampNs <= nowElapsedRealtimeNs) {
            // Keep a generous budget for watch sensor batching or main-thread delays, but
            // never interpret hours-old buffered movement as a fresh wrist gesture.
            if (nowElapsedRealtimeNs - timestampNs > MAX_SAMPLE_AGE_NS) return false
        } else {
            // Allow small sensor/clock scheduling skew; fail closed for future timestamps.
            if (timestampNs - nowElapsedRealtimeNs > MAX_FUTURE_SKEW_NS) return false
        }

        lastAcceptedTimestampNs = timestampNs
        return true
    }

    fun reset() {
        lastAcceptedTimestampNs = 0L
    }

    companion object {
        internal const val MAX_SAMPLE_AGE_NS = 10_000_000_000L
        internal const val MAX_FUTURE_SKEW_NS = 100_000_000L
    }
}
