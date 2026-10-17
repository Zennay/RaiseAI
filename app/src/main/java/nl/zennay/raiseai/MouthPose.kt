package nl.zennay.raiseai

import kotlin.math.sqrt

data class MouthPose(val x: Float, val y: Float, val z: Float) {
    companion object {
        private const val MIN_VECTOR_LENGTH = 0.001f

        fun normalizedOrNull(x: Float, y: Float, z: Float): MouthPose? {
            if (!x.isFinite() || !y.isFinite() || !z.isFinite()) return null

            val length = sqrt(x * x + y * y + z * z)
            if (!length.isFinite() || length < MIN_VECTOR_LENGTH) return null

            return MouthPose(x / length, y / length, z / length)
        }
    }
}
