package nl.zennay.raiseai

import android.content.Context
import java.io.File
import java.io.IOException

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
    private const val MAX_TRIAL_FILE_BYTES = 2L * 1024L * 1024L

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
                SensorTrialCsvPolicy.HEADER + "\n"
            )
        }
        file.appendText(
            "$label,$sessionId,$durationMs,$sampleCount,$detectorTriggered,$maxSimilarity,$appVersion,$sourceRevision,$detectorConfig\n"
        )
    }

    fun trialCount(context: Context): Int {
        val accepted = progress(context)
        return accepted.mouthTrials + accepted.nonTriggerTrials
    }

    fun progress(context: Context): SensorTrialProgress {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) return SensorTrialProgress()
        // Corrupted local capture storage must not crash the Watch setup screen, or block
        // on a non-regular path. An unreadable/oversized dataset can never be a V1 PASS.
        if (!file.isFile || file.length() > MAX_TRIAL_FILE_BYTES) {
            return SensorTrialProgress(rejectedTrials = 1)
        }
        return try {
            file.useLines { lines -> SensorTrialCsvPolicy.evaluate(lines) }
        } catch (_: IOException) {
            SensorTrialProgress(rejectedTrials = 1)
        } catch (_: SecurityException) {
            SensorTrialProgress(rejectedTrials = 1)
        }
    }

    fun clear(context: Context) {
        File(context.filesDir, FILE_NAME).delete()
    }
}
