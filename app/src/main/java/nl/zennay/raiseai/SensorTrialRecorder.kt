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
            rejectedTrials == 0 &&
            mouthTrials >= 30 &&
            mouthDetections in 0..mouthTrials &&
            nonTriggerTrials >= 100 &&
            falseTriggers in 0..nonTriggerTrials &&
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
        sourceRevision: String,
        detectorConfig: String
    ) {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) {
            file.writeText(
                "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity,app_version,source_revision,detector_config\n"
            )
        }
        file.appendText(
            "$label,$sessionId,$durationMs,$sampleCount,$detectorTriggered,$maxSimilarity,$appVersion,$sourceRevision,$detectorConfig\n"
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

        return file.useLines { lines -> SensorTrialCsvPolicy.evaluate(lines) }
    }

    fun clear(context: Context) {
        File(context.filesDir, FILE_NAME).delete()
    }
}
