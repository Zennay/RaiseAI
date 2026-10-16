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
        // A sensor driver can return finite but impossible magnitudes. Letting a giant
        // impulse reach the detector overflows Float square/square-root calculations and
        // corrupts its persistent gravity estimate. Measure squared magnitude in Double
        // without allocating on this hot 10 Hz path; real Watch raises stay far below 50g.
        val x = values[0].toDouble()
        val y = values[1].toDouble()
        val z = values[2].toDouble()
        if (x * x + y * y + z * z > MAX_SENSOR_MAGNITUDE_SQUARED) return false
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
        // >50g is outside intentional wrist movement, even allowing for impact spikes.
        internal const val MAX_SENSOR_MAGNITUDE_MS2 = 500.0
        private const val MAX_SENSOR_MAGNITUDE_SQUARED =
            MAX_SENSOR_MAGNITUDE_MS2 * MAX_SENSOR_MAGNITUDE_MS2
        internal const val MAX_SAMPLE_AGE_NS = 10_000_000_000L
        internal const val MAX_FUTURE_SKEW_NS = 100_000_000L
    }
}
