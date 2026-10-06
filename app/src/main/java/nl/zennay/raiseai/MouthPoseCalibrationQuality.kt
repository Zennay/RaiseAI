package nl.zennay.raiseai

import kotlin.math.sqrt

internal enum class CalibrationFailure {
    TOO_FEW_SAMPLES,
    INVALID_SAMPLE,
    GRAVITY_OUT_OF_RANGE,
    TOO_MUCH_MOTION,
    UNSTABLE_ORIENTATION
}

internal data class CalibrationAssessment(
    val pose: MouthPose?,
    val failure: CalibrationFailure?
) {
    init {
        require((pose == null) != (failure == null)) {
            "Calibration assessment must contain exactly one of pose or failure"
        }
    }

    val accepted: Boolean
        get() = pose != null
}

internal object MouthPoseCalibrationQuality {
    const val MIN_SAMPLES = 8
    private const val MIN_MEAN_GRAVITY = 7.0f
    private const val MAX_MEAN_GRAVITY = 12.5f
    private const val MAX_MAGNITUDE_STDDEV = 1.25f
    private const val MIN_ORIENTATION_COHERENCE = 0.97f
    private const val MIN_VECTOR_LENGTH = 0.001f

    fun evaluate(samples: List<FloatArray>): CalibrationAssessment {
        if (samples.size < MIN_SAMPLES) {
            return rejected(CalibrationFailure.TOO_FEW_SAMPLES)
        }

        data class Sample(
            val x: Float,
            val y: Float,
            val z: Float,
            val magnitude: Float
        )

        val parsed = ArrayList<Sample>(samples.size)
        for (values in samples) {
            if (values.size < 3) {
                return rejected(CalibrationFailure.INVALID_SAMPLE)
            }

            val x = values[0]
            val y = values[1]
            val z = values[2]
            if (!x.isFinite() || !y.isFinite() || !z.isFinite()) {
                return rejected(CalibrationFailure.INVALID_SAMPLE)
            }

            val magnitude = sqrt(x * x + y * y + z * z)
            if (!magnitude.isFinite() || magnitude < MIN_VECTOR_LENGTH) {
                return rejected(CalibrationFailure.INVALID_SAMPLE)
            }

            parsed += Sample(x, y, z, magnitude)
        }

        val meanMagnitude = parsed.map { it.magnitude }.average().toFloat()
        if (meanMagnitude !in MIN_MEAN_GRAVITY..MAX_MEAN_GRAVITY) {
            return rejected(CalibrationFailure.GRAVITY_OUT_OF_RANGE)
        }

        val magnitudeVariance = parsed
            .map { sample ->
                val delta = sample.magnitude - meanMagnitude
                delta * delta
            }
            .average()
            .toFloat()
        val magnitudeStdDev = sqrt(magnitudeVariance)
        if (magnitudeStdDev > MAX_MAGNITUDE_STDDEV) {
            return rejected(CalibrationFailure.TOO_MUCH_MOTION)
        }

        val meanX = parsed.map { it.x }.average().toFloat()
        val meanY = parsed.map { it.y }.average().toFloat()
        val meanZ = parsed.map { it.z }.average().toFloat()
        val meanLength = sqrt(meanX * meanX + meanY * meanY + meanZ * meanZ)
        if (!meanLength.isFinite() || meanLength < MIN_VECTOR_LENGTH) {
            return rejected(CalibrationFailure.UNSTABLE_ORIENTATION)
        }

        val pose = MouthPose(meanX / meanLength, meanY / meanLength, meanZ / meanLength)
        val coherence = parsed
            .map { sample ->
                (sample.x / sample.magnitude) * pose.x +
                    (sample.y / sample.magnitude) * pose.y +
                    (sample.z / sample.magnitude) * pose.z
            }
            .average()
            .toFloat()

        if (!coherence.isFinite() || coherence < MIN_ORIENTATION_COHERENCE) {
            return rejected(CalibrationFailure.UNSTABLE_ORIENTATION)
        }

        return CalibrationAssessment(pose = pose, failure = null)
    }

    private fun rejected(failure: CalibrationFailure) =
        CalibrationAssessment(pose = null, failure = failure)
}
