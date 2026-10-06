package nl.zennay.raiseai

import org.json.JSONObject
import java.io.IOException
import java.net.URL
import javax.net.ssl.HttpsURLConnection

class GatewayClient(private val settings: GatewaySettings) {

    fun send(text: String): GatewayResponse {
        val connection = URL(settings.baseUrl + "/v1/assistant")
            .openConnection() as HttpsURLConnection

        try {
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
            val responseStream = if (code in 200..299) {
                connection.inputStream
            } else {
                connection.errorStream
            }
            val responseText = responseStream
                ?.use { GatewayResponsePolicy.readUtf8Bounded(it) }
                .orEmpty()

            if (code !in 200..299) {
                throw IOException("gateway_http_$code")
            }
            if (responseText.isBlank()) {
                throw IOException("gateway_empty_response")
            }

            val json = try {
                JSONObject(responseText)
            } catch (error: Exception) {
                throw IOException("gateway_invalid_json", error)
            }
            val execution = json.optJSONObject("execution")
                ?: throw IOException("gateway_response_missing_execution")

            return GatewayResponsePolicy.validate(
                route = json.opt("route") as? String,
                status = json.opt("status") as? String,
                executionEnabled = execution.optBoolean("enabled", false),
                executionReason = execution.opt("reason") as? String,
                answer = (json.opt("answer") as? String)
                    ?: (json.opt("message") as? String)
            )
        } finally {
            connection.disconnect()
        }
    }
}
