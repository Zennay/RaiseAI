package nl.zennay.raiseai

import android.content.Context
import java.io.File

data class SensorTrialProgress(
    val mouthTrials: Int = 0,
    val mouthDetections: Int = 0,
    val nonTriggerTrials: Int = 0,
    val falseTriggers: Int = 0,
    val rejectedTrials: Int = 0,
    val mixedEvidenceIdentity: Boolean = false
) {
    val detectionRate: Float
        get() = if (mouthTrials == 0) 0f else mouthDetections.toFloat() / mouthTrials

    val falseTriggerRate: Float
        get() = if (nonTriggerTrials == 0) 0f else falseTriggers.toFloat() / nonTriggerTrials

    val v1GatePassed: Boolean
        get() = !mixedEvidenceIdentity &&
            mouthTrials >= 30 &&
            nonTriggerTrials >= 100 &&
            detectionRate >= 0.90f &&
            falseTriggerRate <= 0.05f
}

object SensorTrialRecorder {
    private const val FILE_NAME = "sensor-trials.csv"
    private const val MIN_QUALIFYING_DURATION_MS = 3_000L
    private const val MIN_QUALIFYING_SAMPLES = 20

    @Synchronized
    fun append(
        context: Context,
        label: String,
        sessionId: Long,
        durationMs: Long,
        sampleCount: Int,
        detectorTriggered: Boolean,
        maxSimilarity: Float,
        appVersion: String,
        detectorConfig: String
    ) {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) {
            file.writeText(
                "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity,app_version,detector_config\n"
            )
        }
        file.appendText(
            "$label,$sessionId,$durationMs,$sampleCount,$detectorTriggered,$maxSimilarity,$appVersion,$detectorConfig\n"
        )
    }

    fun trialCount(context: Context): Int {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) return 0
        return (file.useLines { it.count() } - 1).coerceAtLeast(0)
    }

    fun progress(context: Context): SensorTrialProgress {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) return SensorTrialProgress()

        var mouthTrials = 0
        var mouthDetections = 0
        var nonTriggerTrials = 0
        var falseTriggers = 0
        var rejectedTrials = 0
        val identities = mutableSetOf<String>()

        file.useLines { lines ->
            lines.drop(1).forEach { line ->
                val fields = line.split(',', limit = 8)
                if (fields.size != 8) {
                    rejectedTrials++
                    return@forEach
                }

                val label = fields[0]
                val durationMs = fields[2].toLongOrNull()
                val sampleCount = fields[3].toIntOrNull()
                val triggered = when (fields[4]) {
                    "true" -> true
                    "false" -> false
                    else -> null
                }
                val appVersion = fields[6]
                val detectorConfig = fields[7]

                if (durationMs == null || sampleCount == null || triggered == null ||
                    appVersion.isBlank() || detectorConfig.isBlank() || detectorConfig == "missing"
                ) {
                    rejectedTrials++
                    return@forEach
                }

                if (durationMs < MIN_QUALIFYING_DURATION_MS || sampleCount < MIN_QUALIFYING_SAMPLES) {
                    rejectedTrials++
                    return@forEach
                }

                identities += "$appVersion|$detectorConfig"
                when (label) {
                    "mouth_raise" -> {
                        mouthTrials++
                        if (triggered) mouthDetections++
                    }
                    "view_time", "normal_move" -> {
                        nonTriggerTrials++
                        if (triggered) falseTriggers++
                    }
                    else -> rejectedTrials++
                }
            }
        }

        return SensorTrialProgress(
            mouthTrials = mouthTrials,
            mouthDetections = mouthDetections,
            nonTriggerTrials = nonTriggerTrials,
            falseTriggers = falseTriggers,
            rejectedTrials = rejectedTrials,
            mixedEvidenceIdentity = identities.size > 1
        )
    }

    fun clear(context: Context) {
        File(context.filesDir, FILE_NAME).delete()
    }
}
