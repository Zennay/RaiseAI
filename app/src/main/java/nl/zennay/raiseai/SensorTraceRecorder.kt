package nl.zennay.raiseai

import android.content.Context
import java.io.File

object SensorTraceRecorder {
    private const val FILE_NAME = "sensor-traces.csv"

    @Synchronized
    fun append(
        context: Context,
        label: String,
        sessionId: Long,
        elapsedMs: Long,
        x: Float,
        y: Float,
        z: Float
    ) {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) {
            file.writeText("label,session_id,elapsed_ms,x,y,z\n")
        }
        file.appendText(
            "$label,$sessionId,$elapsedMs,$x,$y,$z\n"
        )
    }

    fun sampleCount(context: Context): Int {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) return 0
        return (file.useLines { it.count() } - 1).coerceAtLeast(0)
    }

    fun clear(context: Context) {
        File(context.filesDir, FILE_NAME).delete()
    }
}
