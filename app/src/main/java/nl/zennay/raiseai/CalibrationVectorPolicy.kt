package nl.zennay.raiseai

import kotlin.math.sqrt

/**
 * Pure accelerometer calibration boundary. Sensor callbacks and persisted values are untrusted:
 * a vector used by the raise detector must be finite and physically plausible before it can
 * become a unit pose. The Android storage and activity owner can adopt this without depending
 * on Android framework classes.
 *
 * This policy is intentionally not wired into CalibrationStore while its existing PR owns that
 * file. A rejected sample must leave any previously saved pose unchanged.
 */
object CalibrationVectorPolicy {
    private const val MIN_MAGNITUDE = 0.001
    // Above ~20g is outside the intended Watch accelerometer calibration envelope.
    private const val MAX_MAGNITUDE = 200.0
    private const val UNIT_TOLERANCE = 0.02

    fun normalize(x: Float, y: Float, z: Float): MouthPose? {
        if (!x.isFinite() || !y.isFinite() || !z.isFinite()) return null

        // Widen before squaring; Float squared can overflow even when the input is finite.
        val dx = x.toDouble()
        val dy = y.toDouble()
        val dz = z.toDouble()
        val magnitude = sqrt(dx * dx + dy * dy + dz * dz)
        if (!magnitude.isFinite() || magnitude < MIN_MAGNITUDE ||
            magnitude > MAX_MAGNITUDE
        ) return null

        val pose = MouthPose(
            (dx / magnitude).toFloat(),
            (dy / magnitude).toFloat(),
            (dz / magnitude).toFloat()
        )
        return pose.takeIf(::isUsableUnitPose)
    }

    /**
     * Validate a stored pose, not merely the sample from which it was derived. Corrupted
     * SharedPreferences entries or partial prior writes must never qualify as calibration.
     */
    fun isUsableUnitPose(pose: MouthPose?): Boolean {
        if (pose == null) return false
        if (!pose.x.isFinite() || !pose.y.isFinite() || !pose.z.isFinite()) return false

        val x = pose.x.toDouble()
        val y = pose.y.toDouble()
        val z = pose.z.toDouble()
        val magnitude = sqrt(x * x + y * y + z * z)
        return magnitude.isFinite() &&
            magnitude >= (1.0 - UNIT_TOLERANCE) &&
            magnitude <= (1.0 + UNIT_TOLERANCE)
    }
}
