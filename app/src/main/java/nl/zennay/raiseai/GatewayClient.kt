package nl.zennay.raiseai

import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.URL
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import javax.net.ssl.HttpsURLConnection

data class GatewayResponse(
    val route: String,
    val status: String,
    val executionEnabled: Boolean,
    val executionReason: String?,
    val answer: String?
)

internal object GatewayResponseBodyReader {
    const val MAX_RESPONSE_BYTES = 64 * 1024

    fun read(stream: InputStream?): String {
        if (stream == null) return ""

        return stream.use { input ->
            val output = ByteArrayOutputStream()
            val buffer = ByteArray(4 * 1024)
            var totalBytes = 0

            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                if (read == 0) continue

                totalBytes += read
                if (totalBytes > MAX_RESPONSE_BYTES) {
                    throw IOException("gateway_response_too_large")
                }
                output.write(buffer, 0, read)
            }

            decodeUtf8(output.toByteArray())
        }
    }

    private fun decodeUtf8(bytes: ByteArray): String =
        try {
            Charsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString()
        } catch (error: CharacterCodingException) {
            throw IOException("gateway_response_invalid_utf8", error)
        }
}

private fun JSONObject.optionalValue(name: String): Any? =
    opt(name).takeUnless { it === JSONObject.NULL }

class GatewayClient(private val settings: GatewaySettings) {

    fun send(text: String): GatewayResponse {
        val connection = URL(settings.baseUrl + "/v1/assistant")
            .openConnection() as HttpsURLConnection

        return try {
            settings.spkiSha256?.let { pin ->
                connection.sslSocketFactory = PinnedTls.socketFactory(pin)
            }

            connection.requestMethod = "POST"
            connection.connectTimeout = 2_500
            connection.readTimeout = 8_000
            connection.instanceFollowRedirects = false
            connection.doOutput = true
            connection.setRequestProperty("Authorization", "Bearer ${settings.token}")
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("Accept", "application/json")

            val payload = JSONObject()
                .put("text", text)
                .put("locale", "nl-NL")
                .put("device", "galaxy-watch-7")
                .toString()

            connection.outputStream.use { stream ->
                stream.write(payload.toByteArray(Charsets.UTF_8))
            }

            val code = connection.responseCode
            val successful = code in 200..299
            if (successful) {
                GatewayResponseMetadataPolicy.validateSuccessfulResponse(
                    connection.contentType,
                    connection.contentLengthLong
                )
            }

            val responseText = GatewayResponseBodyReader.read(
                if (successful) connection.inputStream else connection.errorStream
            )

            if (!successful) {
                throw IOException("gateway_http_$code")
            }

            val json = JSONObject(responseText)
            val execution = when (val value = json.optionalValue("execution")) {
                null -> null
                is JSONObject -> value
                else -> GatewayResponseFieldPolicy.invalidSchema()
            }

            GatewayResponse(
                route = GatewayResponseFieldPolicy.stringOrDefault(
                    json.optionalValue("route"),
                    "unknown"
                ),
                status = GatewayResponseFieldPolicy.stringOrDefault(
                    json.optionalValue("status"),
                    "unknown"
                ),
                executionEnabled = GatewayResponseFieldPolicy.booleanOrDefault(
                    execution?.optionalValue("enabled"),
                    false
                ),
                executionReason = GatewayResponseFieldPolicy.optionalNonBlankString(
                    execution?.optionalValue("reason")
                ),
                answer = GatewayResponseFieldPolicy.optionalNonBlankString(
                    json.optionalValue("answer")
                ) ?: GatewayResponseFieldPolicy.optionalNonBlankString(
                    json.optionalValue("message")
                )
            )
        } finally {
            connection.disconnect()
        }
    }
}
