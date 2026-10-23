package nl.zennay.raiseai

/**
 * One validated ingress for a single registered accelerometer stream.
 *
 * A rejected sample never reaches the stateful gesture detector, and does not consume an
 * ordering slot. The Android Service owner can replace its direct event indexing with this
 * adapter once the concurrent Service PRs have settled.
 *
 * One adapter belongs to one registration. After a pause, use [restartWithFreshDetector] to
 * discard *both* timestamps and old detector gravity/movement/cooldown state. Resetting just the
 * ordering policy could mistake a sensor wake-up for a real new wrist motion.
 */
internal class VerifiedAccelerometerStream(
    private var detector: RaiseGestureDetector,
    private val policy: AccelerometerEventOrderPolicy = AccelerometerEventOrderPolicy()
) {
    /** Null means "drop invalid sample without modifying the gesture state". */
    fun process(
        values: FloatArray?,
        timestampNs: Long,
        nowElapsedRealtimeNs: Long,
        mouthPose: MouthPose?
    ): DetectionDebug? {
        if (!policy.accept(values, timestampNs, nowElapsedRealtimeNs)) return null

        // The policy guarantees non-null, three finite/plausible axes and valid timestamp.
        val axes = requireNotNull(values)
        return detector.onAccelerometer(
            axes[0], axes[1], axes[2], timestampNs / NANOS_PER_MILLI, mouthPose
        )
    }

    /**
     * Start a new sensor registration with a fresh detector configured to the same user thresholds.
     * Reject reuse of the previous detector: its filter/gesture state belongs to the old session.
     * Do not call per sample or after an ordinary batched delivery.
     */
    fun restartWithFreshDetector(freshDetector: RaiseGestureDetector) {
        require(freshDetector !== detector) { "Sensor registration needs a fresh detector" }
        detector = freshDetector
        policy.reset()
    }

    private companion object {
        const val NANOS_PER_MILLI = 1_000_000L
    }
}
