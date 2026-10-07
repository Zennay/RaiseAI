package nl.zennay.raiseai

import kotlin.math.sqrt

object CalibrationPosePolicy {
    private const val MIN_VECTOR_LENGTH = 0.001f

    fun normalizeOrNull(x: Float, y: Float, z: Float): MouthPose? {
        if (!x.isFinite() || !y.isFinite() || !z.isFinite()) return null

        val lengthSquared = x * x + y * y + z * z
        if (!lengthSquared.isFinite() || lengthSquared < MIN_VECTOR_LENGTH * MIN_VECTOR_LENGTH) {
            return null
        }

        val length = sqrt(lengthSquared.toDouble()).toFloat()
        if (!length.isFinite() || length < MIN_VECTOR_LENGTH) return null

        return MouthPose(x / length, y / length, z / length)
    }
}
