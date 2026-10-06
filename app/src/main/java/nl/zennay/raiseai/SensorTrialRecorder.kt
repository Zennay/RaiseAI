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
        get() = rejectedTrials == 0 &&
            !mixedEvidenceIdentity &&
            mouthDetections in 0..mouthTrials &&
            falseTriggers in 0..nonTriggerTrials &&
            mouthTrials >= 30 &&
            nonTriggerTrials >= 100 &&
            detectionRate >= 0.90f &&
            falseTriggerRate <= 0.05f
}

object SensorTrialRecorder {
    private const val FILE_NAME = "sensor-trials.csv"
    internal const val HEADER =
        "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity,app_version,source_revision,detector_config"
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
        ensureHeader(file)
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
        return file.useLines { lines -> summarizeRows(lines) }
    }

    internal fun summarizeRows(lines: Sequence<String>): SensorTrialProgress {
        val allLines = lines.toList()
        if (allLines.isEmpty()) return SensorTrialProgress()
        if (allLines.first() != HEADER) {
            return SensorTrialProgress(rejectedTrials = 1)
        }

        var mouthTrials = 0
        var mouthDetections = 0
        var nonTriggerTrials = 0
        var falseTriggers = 0
        var rejectedTrials = 0
        val identities = mutableSetOf<String>()
        val seenSessionIds = mutableSetOf<Long>()

        allLines.drop(1).forEach { line ->
            val fields = line.split(',', limit = 10)
            if (fields.size != 9) {
                rejectedTrials++
                return@forEach
            }

            val label = fields[0]
            val sessionId = fields[1].toLongOrNull()
            val durationMs = fields[2].toLongOrNull()
            val sampleCount = fields[3].toIntOrNull()
            val triggered = when (fields[4]) {
                "true" -> true
                "false" -> false
                else -> null
            }
            val maxSimilarity = fields[5].toFloatOrNull()
            val appVersion = fields[6]
            val sourceRevision = fields[7].lowercase()
            val detectorConfig = fields[8]

            if (sessionId == null || sessionId <= 0L ||
                durationMs == null || sampleCount == null || triggered == null ||
                maxSimilarity == null || !maxSimilarity.isFinite() || maxSimilarity !in -1f..1f ||
                appVersion.isBlank() ||
                !sourceRevision.matches(Regex("^[0-9a-f]{40}$")) ||
                detectorConfig.isBlank() || detectorConfig == "missing"
            ) {
                rejectedTrials++
                return@forEach
            }

            if (!seenSessionIds.add(sessionId)) {
                rejectedTrials++
                return@forEach
            }

            if (durationMs < MIN_QUALIFYING_DURATION_MS || sampleCount < MIN_QUALIFYING_SAMPLES) {
                rejectedTrials++
                return@forEach
            }

            val knownLabel = label == "mouth_raise" ||
                label == "view_time" ||
                label == "normal_move"
            if (!knownLabel) {
                rejectedTrials++
                return@forEach
            }

            identities += "$appVersion|$sourceRevision|$detectorConfig"
            when (label) {
                "mouth_raise" -> {
                    mouthTrials++
                    if (triggered) mouthDetections++
                }
                "view_time", "normal_move" -> {
                    nonTriggerTrials++
                    if (triggered) falseTriggers++
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

    internal fun ensureHeader(file: File) {
        if (!file.exists() || file.length() == 0L) {
            file.writeText("$HEADER\n")
        }
    }

    fun clear(context: Context) {
        File(context.filesDir, FILE_NAME).delete()
    }
}
