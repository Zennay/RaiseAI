package nl.zennay.raiseai

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream

data class GatewayResponse(
    val route: String,
    val status: String,
    val executionEnabled: Boolean,
    val executionReason: String?,
    val answer: String?
)

internal object GatewayResponsePolicy {
    const val MAX_RESPONSE_BYTES = 64 * 1024
    private const val MAX_ROUTE_CHARS = 64
    private const val MAX_REASON_CHARS = 512
    private const val MAX_ANSWER_CHARS = 16 * 1024

    fun readUtf8Bounded(
        input: InputStream,
        maxBytes: Int = MAX_RESPONSE_BYTES
    ): String {
        require(maxBytes > 0) { "maxBytes must be > 0" }

        val output = ByteArrayOutputStream(minOf(maxBytes, 4096))
        val buffer = ByteArray(4096)
        var total = 0

        while (true) {
            val read = input.read(buffer)
            if (read == -1) break
            total += read
            if (total > maxBytes) {
                throw IOException("gateway_response_too_large")
            }
            output.write(buffer, 0, read)
        }

        return output.toString(Charsets.UTF_8.name())
    }

    fun validate(
        route: String?,
        status: String?,
        executionEnabled: Boolean,
        executionReason: String?,
        answer: String?
    ): GatewayResponse {
        val normalizedRoute = route?.trim().orEmpty()
        if (normalizedRoute.isEmpty()) {
            throw IOException("gateway_response_missing_route")
        }
        if (normalizedRoute.length > MAX_ROUTE_CHARS) {
            throw IOException("gateway_response_route_too_long")
        }

        val normalizedStatus = status?.trim().orEmpty()
        if (normalizedStatus !in setOf("answered", "routed")) {
            throw IOException("gateway_response_invalid_status")
        }

        val normalizedReason = executionReason
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
        if ((normalizedReason?.length ?: 0) > MAX_REASON_CHARS) {
            throw IOException("gateway_response_reason_too_long")
        }

        val normalizedAnswer = answer
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
        if ((normalizedAnswer?.length ?: 0) > MAX_ANSWER_CHARS) {
            throw IOException("gateway_response_answer_too_long")
        }

        if (normalizedStatus == "answered" && normalizedAnswer == null) {
            throw IOException("gateway_response_missing_answer")
        }
        if (normalizedStatus == "routed" && normalizedAnswer != null) {
            throw IOException("gateway_response_ambiguous_answer")
        }

        return GatewayResponse(
            route = normalizedRoute,
            status = normalizedStatus,
            executionEnabled = executionEnabled,
            executionReason = normalizedReason,
            answer = normalizedAnswer
        )
    }
}
