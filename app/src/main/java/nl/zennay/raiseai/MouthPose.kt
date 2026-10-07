package nl.zennay.raiseai

import kotlin.math.sqrt

data class MouthPose(val x: Float, val y: Float, val z: Float) {
    /**
     * Returns this pose as a finite unit vector, or null when it cannot safely
     * represent a calibrated wrist orientation.
     *
     * The magnitude is computed in Double precision so large-but-finite Float
     * components cannot overflow while being squared.
     */
    fun normalizedOrNull(): MouthPose? {
        if (!x.isFinite() || !y.isFinite() || !z.isFinite()) return null

        val dx = x.toDouble()
        val dy = y.toDouble()
        val dz = z.toDouble()
        val lengthSquared = dx * dx + dy * dy + dz * dz
        if (!lengthSquared.isFinite()) return null

        val length = sqrt(lengthSquared)
        if (!length.isFinite() || length < MIN_VALID_MAGNITUDE) return null

        val normalized = MouthPose(
            (dx / length).toFloat(),
            (dy / length).toFloat(),
            (dz / length).toFloat()
        )
        if (!normalized.x.isFinite() || !normalized.y.isFinite() || !normalized.z.isFinite()) {
            return null
        }
        return normalized
    }

    private companion object {
        const val MIN_VALID_MAGNITUDE = 0.001
    }
}
