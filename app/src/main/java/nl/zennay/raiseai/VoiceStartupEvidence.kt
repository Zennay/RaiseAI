package nl.zennay.raiseai

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.time.Instant

object VoiceStartupEvidence {
    const val FILE_NAME = "voice-startup-evidence.json"

    fun elapsedMs(requestedElapsedMs: Long, readyElapsedMs: Long): Long =
        (readyElapsedMs - requestedElapsedMs).coerceAtLeast(0L)

    fun record(
        context: Context,
        attempt: Int,
        listenRequestToReadyMs: Long
    ) {
        val payload = JSONObject()
            .put("schema_version", 1)
            .put("recorded_at_utc", Instant.now().toString())
            .put("app_version", BuildConfig.VERSION_NAME)
            .put("source_revision", BuildConfig.SOURCE_REVISION)
            .put("attempt", attempt.coerceAtLeast(1))
            .put("listen_request_to_ready_ms", listenRequestToReadyMs.coerceAtLeast(0L))

        write(context, payload)
    }

    private fun write(context: Context, payload: JSONObject) {
        val destination = File(context.filesDir, FILE_NAME)
        val temporary = File(context.filesDir, "$FILE_NAME.tmp")
        val serialized = payload.toString() + "\n"

        synchronized(this) {
            temporary.writeText(serialized, Charsets.UTF_8)
            if (destination.exists()) {
                destination.delete()
            }
            if (!temporary.renameTo(destination)) {
                destination.writeText(serialized, Charsets.UTF_8)
                temporary.delete()
            }
        }
    }
}
