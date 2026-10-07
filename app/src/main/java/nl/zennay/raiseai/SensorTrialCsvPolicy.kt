package nl.zennay.raiseai

internal data class ParsedSensorTrialRow(
    val label: String,
    val sessionId: Long,
    val durationMs: Long,
    val sampleCount: Int,
    val detectorTriggered: Boolean,
    val maxSimilarity: Float,
    val appVersion: String,
    val sourceRevision: String,
    val detectorConfig: String
)

internal object SensorTrialCsvPolicy {
    const val HEADER =
        "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity,app_version,source_revision,detector_config"

    private val allowedLabels = setOf("mouth_raise", "view_time", "normal_move")
    private val sourceRevisionPattern = Regex("^[0-9a-f]{40}$")

    fun hasCanonicalHeader(line: String): Boolean = line == HEADER

    fun parseRow(line: String): ParsedSensorTrialRow? {
        if (line.count { it == ',' } != 8) return null

        val fields = line.split(',', limit = 9)
        if (fields.size != 9) return null

        val label = fields[0]
        if (label !in allowedLabels) return null

        val sessionId = fields[1].toLongOrNull() ?: return null
        val durationMs = fields[2].toLongOrNull() ?: return null
        val sampleCount = fields[3].toIntOrNull() ?: return null
        val detectorTriggered = when (fields[4]) {
            "true" -> true
            "false" -> false
            else -> return null
        }
        val maxSimilarity = fields[5].toFloatOrNull() ?: return null
        val appVersion = fields[6]
        val sourceRevision = fields[7].lowercase()
        val detectorConfig = fields[8]

        if (sessionId <= 0L ||
            durationMs < 0L ||
            sampleCount < 0 ||
            !maxSimilarity.isFinite() ||
            appVersion.isBlank() ||
            !sourceRevision.matches(sourceRevisionPattern) ||
            detectorConfig.isBlank() ||
            detectorConfig == "missing"
        ) {
            return null
        }

        return ParsedSensorTrialRow(
            label = label,
            sessionId = sessionId,
            durationMs = durationMs,
            sampleCount = sampleCount,
            detectorTriggered = detectorTriggered,
            maxSimilarity = maxSimilarity,
            appVersion = appVersion,
            sourceRevision = sourceRevision,
            detectorConfig = detectorConfig
        )
    }
}
