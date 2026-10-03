package nl.zennay.raiseai

import android.content.Context
import java.io.File

object SensorTrialRecorder {
    private const val FILE_NAME = "sensor-trials.csv"

    @Synchronized
    fun append(
        context: Context,
        label: String,
        sessionId: Long,
        durationMs: Long,
        sampleCount: Int,
        detectorTriggered: Boolean,
        maxSimilarity: Float
    ) {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) {
            file.writeText(
                "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity\n"
            )
        }
        file.appendText(
            "$label,$sessionId,$durationMs,$sampleCount,$detectorTriggered,$maxSimilarity\n"
        )
    }

    fun trialCount(context: Context): Int {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) return 0
        return (file.useLines { it.count() } - 1).coerceAtLeast(0)
    }

    fun clear(context: Context) {
        File(context.filesDir, FILE_NAME).delete()
    }
}
