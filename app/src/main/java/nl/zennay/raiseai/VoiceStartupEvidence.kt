package nl.zennay.raiseai

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.time.Instant

object VoiceStartupEvidence {
    const val FILE_NAME = "voice-startup-evidence.json"
    const val HISTORY_FILE_NAME = "voice-startup-evidence.jsonl"
    internal const val MAX_HISTORY_SAMPLES = 50

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

        val serialized = payload.toString()
        synchronized(this) {
            writeAtomically(
                destination = File(context.filesDir, FILE_NAME),
                content = serialized + "\n"
            )
            appendHistory(context, serialized)
        }
    }

    internal fun boundedHistory(
        existingLines: List<String>,
        newLine: String,
        maxSamples: Int = MAX_HISTORY_SAMPLES
    ): List<String> {
        require(maxSamples > 0) { "maxSamples must be > 0" }
        return (existingLines.filter { it.isNotBlank() } + newLine.trim())
            .takeLast(maxSamples)
    }

    private fun appendHistory(context: Context, serialized: String) {
        val destination = File(context.filesDir, HISTORY_FILE_NAME)
        val existing = if (destination.exists()) {
            destination.readLines(Charsets.UTF_8)
        } else {
            emptyList()
        }
        val lines = boundedHistory(existing, serialized)
        writeAtomically(destination, lines.joinToString(separator = "\n", postfix = "\n"))
    }

    private fun writeAtomically(destination: File, content: String) {
        val temporary = File(destination.parentFile, "${destination.name}.tmp")
        temporary.writeText(content, Charsets.UTF_8)
        if (destination.exists()) {
            destination.delete()
        }
        if (!temporary.renameTo(destination)) {
            destination.writeText(content, Charsets.UTF_8)
            temporary.delete()
        }
    }
}
