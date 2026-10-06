package nl.zennay.raiseai

import android.content.Context
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.time.Instant

object WatchE2eEvidence {
    const val FILE_NAME = "watch-e2e-evidence.json"

    fun recordSuccess(
        context: Context,
        inputLengthChars: Int,
        latencyMs: Long,
        response: GatewayResponse
    ) {
        val payload = basePayload("success", inputLengthChars, latencyMs)
            .put("route", safeServerValue(response.route) ?: "unknown")
            .put("status", safeServerValue(response.status) ?: "unknown")
            .put("execution_enabled", response.executionEnabled)
            .put("execution_reason_present", !response.executionReason.isNullOrBlank())
            .put("answer_present", !response.answer.isNullOrBlank())

        write(context, payload)
    }

    fun recordFailure(
        context: Context,
        inputLengthChars: Int,
        latencyMs: Long,
        errorCode: String
    ) {
        val payload = basePayload("failure", inputLengthChars, latencyMs)
            .put("error_code", safeErrorCode(errorCode))

        write(context, payload)
    }

    fun recordFailure(
        context: Context,
        inputLengthChars: Int,
        latencyMs: Long,
        error: Throwable
    ) {
        val message = error.message.orEmpty()
        val code = if (Regex("^gateway_http_\\d{3}$").matches(message)) {
            message
        } else {
            error.javaClass.simpleName.ifBlank { "Throwable" }
        }
        recordFailure(context, inputLengthChars, latencyMs, code)
    }

    private fun basePayload(
        outcome: String,
        inputLengthChars: Int,
        latencyMs: Long
    ): JSONObject = JSONObject()
        .put("schema_version", 2)
        .put("recorded_at_utc", Instant.now().toString())
        .put("app_version", BuildConfig.VERSION_NAME)
        .put("source_revision", BuildConfig.SOURCE_REVISION)
        .put("outcome", outcome)
        .put("input_length_chars", inputLengthChars.coerceAtLeast(0))
        .put("latency_ms", latencyMs.coerceAtLeast(0))

    private fun safeServerValue(value: String?): String? =
        value?.trim()?.take(120)?.takeIf { it.isNotEmpty() }

    private fun safeErrorCode(value: String): String {
        val normalized = value.trim().take(80)
        return if (normalized.matches(Regex("^[A-Za-z0-9_.:-]+$"))) {
            normalized
        } else {
            "gateway_error"
        }
    }

    private fun write(context: Context, payload: JSONObject) {
        val atomicFile = AtomicFile(File(context.filesDir, FILE_NAME))
        val serialized = (payload.toString() + "\n").toByteArray(Charsets.UTF_8)

        synchronized(this) {
            val output = atomicFile.startWrite()
            try {
                output.write(serialized)
                atomicFile.finishWrite(output)
            } catch (error: Throwable) {
                atomicFile.failWrite(output)
                throw error
            }
        }
    }
}
