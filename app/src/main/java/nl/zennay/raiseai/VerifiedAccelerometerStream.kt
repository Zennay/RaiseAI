package nl.zennay.raiseai

/**
 * One validated ingress for a single registered accelerometer stream.
 *
 * A rejected sample never reaches the stateful gesture detector, and does not consume an
 * ordering slot. The Android Service owner can replace its direct event indexing with this
 * adapter once the concurrent Service PRs have settled.
 *
 * Use one adapter per sensor registration lifecycle; call [resetOrdering] after unregistering.
 * This deliberately preserves the detector's existing thresholds and pose/state semantics.
 */
internal class VerifiedAccelerometerStream(
    private val detector: RaiseGestureDetector,
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

    /** Clear replay protection only across sensor unregister/re-register, never per event. */
    fun resetOrdering() = policy.reset()

    private companion object {
        const val NANOS_PER_MILLI = 1_000_000L
    }
}
