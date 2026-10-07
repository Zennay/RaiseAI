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
        return file.useLines(::progressFromLines)
    }

    internal fun progressFromLines(lines: Sequence<String>): SensorTrialProgress {
        var mouthTrials = 0
        var mouthDetections = 0
        var nonTriggerTrials = 0
        var falseTriggers = 0
        var rejectedTrials = 0
        val identities = mutableSetOf<String>()
        val acceptedSessionIdentities = mutableMapOf<Long, String>()

        lines.drop(1).forEach { line ->
                val fields = line.split(',', limit = 9)
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
                    maxSimilarity == null || !maxSimilarity.isFinite() ||
                    appVersion.isBlank() ||
                    !sourceRevision.matches(Regex("^[0-9a-f]{40}$")) ||
                    detectorConfig.isBlank() || detectorConfig == "missing"
                ) {
                    rejectedTrials++
                    return@forEach
                }

                if (durationMs < MIN_QUALIFYING_DURATION_MS || sampleCount < MIN_QUALIFYING_SAMPLES) {
                    rejectedTrials++
                    return@forEach
                }

                val acceptedLabel = when (label) {
                    "mouth_raise" -> true
                    "view_time", "normal_move" -> false
                    else -> {
                        rejectedTrials++
                        return@forEach
                    }
                }

                val evidenceIdentity = "$appVersion|$sourceRevision|$detectorConfig"
                val previousIdentity = acceptedSessionIdentities.putIfAbsent(sessionId, evidenceIdentity)
                if (previousIdentity != null) {
                    if (previousIdentity != evidenceIdentity) {
                        identities += evidenceIdentity
                    }
                    rejectedTrials++
                    return@forEach
                }

                identities += evidenceIdentity
                if (acceptedLabel) {
                    mouthTrials++
                    if (triggered) mouthDetections++
                } else {
                    nonTriggerTrials++
                    if (triggered) falseTriggers++
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
