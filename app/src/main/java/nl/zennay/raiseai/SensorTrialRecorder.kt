package nl.zennay.raiseai

import android.content.Context
import java.io.File

data class SensorTrialProgress(
    val mouthTrials: Int = 0,
    val mouthDetections: Int = 0,
    val nonTriggerTrials: Int = 0,
    val falseTriggers: Int = 0,
    val rejectedTrials: Int = 0,
    val mixedEvidenceIdentity: Boolean = false,
    val unexpectedEvidenceIdentity: Boolean = false,
    val invalidEvidenceStructure: Boolean = false
) {
    val detectionRate: Float
        get() = if (mouthTrials == 0) 0f else mouthDetections.toFloat() / mouthTrials

    val falseTriggerRate: Float
        get() = if (nonTriggerTrials == 0) 0f else falseTriggers.toFloat() / nonTriggerTrials

    val v1GatePassed: Boolean
        get() = !mixedEvidenceIdentity &&
            !unexpectedEvidenceIdentity &&
            !invalidEvidenceStructure &&
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
        if (!file.exists() || file.length() == 0L) {
            file.writeText(SensorTrialCsvPolicy.HEADER + "\n")
        } else if (file.useLines { it.firstOrNull() }?.let(SensorTrialCsvPolicy::hasCanonicalHeader) != true) {
            return
        }

        val rawRow =
            "$label,$sessionId,$durationMs,$sampleCount,$detectorTriggered,$maxSimilarity,$appVersion,$sourceRevision,$detectorConfig"
        val parsed = SensorTrialCsvPolicy.parseRow(rawRow) ?: return
        file.appendText(
            "${parsed.label},${parsed.sessionId},${parsed.durationMs},${parsed.sampleCount}," +
                "${parsed.detectorTriggered},${parsed.maxSimilarity},${parsed.appVersion}," +
                "${parsed.sourceRevision},${parsed.detectorConfig}\n"
        )
    }

    fun trialCount(context: Context): Int {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) return 0
        return trialCount(
            lines = file.readLines(),
            expectedAppVersion = BuildConfig.VERSION_NAME,
            expectedSourceRevision = BuildConfig.SOURCE_REVISION
        )
    }

    internal fun trialCount(
        lines: List<String>,
        expectedAppVersion: String? = null,
        expectedSourceRevision: String? = null
    ): Int {
        if (lines.isEmpty() || !SensorTrialCsvPolicy.hasCanonicalHeader(lines.first())) return 0

        val normalizedExpectedVersion = expectedAppVersion?.trim()
        val normalizedExpectedRevision = expectedSourceRevision?.trim()?.lowercase()
        if (normalizedExpectedVersion != null && normalizedExpectedVersion.isBlank()) return 0
        if (normalizedExpectedRevision != null &&
            !normalizedExpectedRevision.matches(Regex("^[0-9a-f]{40}$"))
        ) return 0

        val seenSessions = mutableSetOf<Long>()
        var count = 0
        lines.drop(1).forEach { line ->
            val parsed = SensorTrialCsvPolicy.parseRow(line) ?: return 0
            if (!seenSessions.add(parsed.sessionId)) return 0
            if (normalizedExpectedVersion != null && parsed.appVersion != normalizedExpectedVersion) return 0
            if (normalizedExpectedRevision != null && parsed.sourceRevision != normalizedExpectedRevision) return 0
            count++
        }
        return count
    }

    fun progress(context: Context): SensorTrialProgress {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) return SensorTrialProgress()
        return progress(
            lines = file.readLines(),
            expectedAppVersion = BuildConfig.VERSION_NAME,
            expectedSourceRevision = BuildConfig.SOURCE_REVISION
        )
    }

    internal fun progress(
        lines: List<String>,
        expectedAppVersion: String? = null,
        expectedSourceRevision: String? = null
    ): SensorTrialProgress {
        if (lines.isEmpty()) return SensorTrialProgress()

        if (!SensorTrialCsvPolicy.hasCanonicalHeader(lines.first())) {
            return SensorTrialProgress(
                rejectedTrials = (lines.size - 1).coerceAtLeast(0),
                invalidEvidenceStructure = true
            )
        }

        var mouthTrials = 0
        var mouthDetections = 0
        var nonTriggerTrials = 0
        var falseTriggers = 0
        val normalizedExpectedVersion = expectedAppVersion?.trim()
        val normalizedExpectedRevision = expectedSourceRevision?.trim()?.lowercase()
        val expectedIdentityIsValid =
            (normalizedExpectedVersion == null || normalizedExpectedVersion.isNotBlank()) &&
                (normalizedExpectedRevision == null ||
                    normalizedExpectedRevision.matches(Regex("^[0-9a-f]{40}$")))

        var rejectedTrials = 0
        var invalidEvidenceStructure = !expectedIdentityIsValid
        var unexpectedEvidenceIdentity = false
        val identities = mutableSetOf<String>()
        val seenSessions = mutableSetOf<Long>()

        lines.drop(1).forEach { line ->
            val parsed = SensorTrialCsvPolicy.parseRow(line)
            if (parsed == null) {
                rejectedTrials++
                invalidEvidenceStructure = true
                return@forEach
            }
            if (!seenSessions.add(parsed.sessionId)) {
                rejectedTrials++
                invalidEvidenceStructure = true
                return@forEach
            }

            identities += "${parsed.appVersion}|${parsed.sourceRevision}|${parsed.detectorConfig}"
            if (normalizedExpectedVersion != null && parsed.appVersion != normalizedExpectedVersion) {
                unexpectedEvidenceIdentity = true
            }
            if (normalizedExpectedRevision != null && parsed.sourceRevision != normalizedExpectedRevision) {
                unexpectedEvidenceIdentity = true
            }

            if (parsed.durationMs < MIN_QUALIFYING_DURATION_MS ||
                parsed.sampleCount < MIN_QUALIFYING_SAMPLES
            ) {
                rejectedTrials++
                return@forEach
            }

            when (parsed.label) {
                "mouth_raise" -> {
                    mouthTrials++
                    if (parsed.detectorTriggered) mouthDetections++
                }
                "view_time", "normal_move" -> {
                    nonTriggerTrials++
                    if (parsed.detectorTriggered) falseTriggers++
                }
            }
        }

        return SensorTrialProgress(
            mouthTrials = mouthTrials,
            mouthDetections = mouthDetections,
            nonTriggerTrials = nonTriggerTrials,
            falseTriggers = falseTriggers,
            rejectedTrials = rejectedTrials,
            mixedEvidenceIdentity = identities.size > 1,
            unexpectedEvidenceIdentity = unexpectedEvidenceIdentity,
            invalidEvidenceStructure = invalidEvidenceStructure
        )
    }

    fun clear(context: Context) {
        File(context.filesDir, FILE_NAME).delete()
    }
}
