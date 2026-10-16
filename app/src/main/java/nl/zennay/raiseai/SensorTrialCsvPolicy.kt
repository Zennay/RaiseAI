package nl.zennay.raiseai

/**
 * Pure parser for the Watch's locally recorded V1 trials.
 *
 * The UI may show progress only for complete, independent, source-bound trials.
 * Corrupted or duplicated rows cannot be used to claim a physical acceptance PASS.
 */
internal data class SensorTrialIdentity(
    val appVersion: String,
    val sourceRevision: String,
    val detectorConfig: String
)

internal object SensorTrialCsvPolicy {
    const val HEADER =
        "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity,app_version,source_revision,detector_config"
    private val REVISION = Regex("^[0-9a-fA-F]{40}$")
    private const val MIN_DURATION_MS = 3_000L
    private const val MIN_SAMPLES = 20

    fun evaluate(lines: Sequence<String>, expected: SensorTrialIdentity? = null): SensorTrialProgress {
        val iterator = lines.iterator()
        if (!iterator.hasNext() || iterator.next() != HEADER) {
            return SensorTrialProgress(rejectedTrials = 1)
        }

        var mouthTrials = 0
        var mouthDetections = 0
        var nonTriggerTrials = 0
        var falseTriggers = 0
        var rejectedTrials = 0
        val identities = mutableSetOf<String>()
        val sessionIds = mutableSetOf<Long>()

        while (iterator.hasNext()) {
            val columns = iterator.next().split(',', limit = 10)
            if (columns.size != 9) {
                rejectedTrials++
                continue
            }

            val label = columns[0]
            val sessionId = columns[1].toLongOrNull()
            val durationMs = columns[2].toLongOrNull()
            val samples = columns[3].toIntOrNull()
            val triggered = when (columns[4]) {
                "true" -> true
                "false" -> false
                else -> null
            }
            val similarity = columns[5].toFloatOrNull()
            val version = columns[6]
            val revision = columns[7]
            val detector = columns[8]

            if (label !in setOf("mouth_raise", "view_time", "normal_move") ||
                sessionId == null || sessionId <= 0L ||
                durationMs == null || durationMs < MIN_DURATION_MS ||
                samples == null || samples < MIN_SAMPLES ||
                triggered == null ||
                similarity == null || !similarity.isFinite() ||
                similarity < -1f || similarity > 1f ||
                version.isBlank() || version.length > 64 ||
                !REVISION.matches(revision) ||
                detector.isBlank() || detector == "missing" || detector.length > 1_024 ||
                (expected != null && (
                    version != expected.appVersion ||
                    !revision.equals(expected.sourceRevision, ignoreCase = true) ||
                    detector != expected.detectorConfig
                ))
            ) {
                rejectedTrials++
                continue
            }

            // A recorded capture session counts once, even when its row is replayed with
            // a different label. Never let duplicate evidence increase both denominators.
            if (!sessionIds.add(sessionId)) {
                rejectedTrials++
                continue
            }
            identities += "$version|${revision.lowercase()}|$detector"

            if (label == "mouth_raise") {
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
}
