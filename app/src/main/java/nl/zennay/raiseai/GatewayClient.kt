package nl.zennay.raiseai

import org.json.JSONObject
import java.io.IOException
import java.net.URL
import javax.net.ssl.HttpsURLConnection

data class GatewayResponse(
    val route: String,
    val status: String,
    val executionEnabled: Boolean,
    val executionReason: String?,
    val answer: String?
)

class GatewayClient(private val settings: GatewaySettings) {

    fun send(text: String): GatewayResponse {
        val connection = URL(settings.baseUrl + "/v1/assistant")
            .openConnection() as HttpsURLConnection

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
        val responseText = (if (code in 200..299) {
            connection.inputStream
        } else {
            connection.errorStream
        })?.bufferedReader()?.use { it.readText() }.orEmpty()

        if (code !in 200..299) {
            throw IOException("gateway_http_$code")
        }

        val json = JSONObject(responseText)
        val execution = json.optJSONObject("execution")

        return GatewayResponse(
            route = json.optString("route", "unknown"),
            status = json.optString("status", "unknown"),
            executionEnabled = execution?.optBoolean("enabled", false) ?: false,
            executionReason = execution?.optString("reason")?.takeIf { it.isNotBlank() },
            answer = json.optString("answer")
                .takeIf { it.isNotBlank() }
                ?: json.optString("message").takeIf { it.isNotBlank() }
        )
    }
}
