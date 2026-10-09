package nl.zennay.raiseai

import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

/**
 * Stable, user-facing feedback for failures in the native Watch -> VPS request.
 *
 * Never surface Throwable.message, Throwable.toString(), URLs, HTTP response
 * bodies, credentials, stack traces, or a server-controlled reason on the Watch.
 * This policy only chooses display copy; it cannot authorize automatic retries.
 */
internal object NativeVoiceFailureFeedbackPolicy {
    internal enum class Category {
        AUTHENTICATION,
        RATE_LIMIT,
        SERVICE_UNAVAILABLE,
        TLS_FAILURE,
        CONNECTION_TIMEOUT,
        CONNECTION_UNAVAILABLE,
        GATEWAY_REJECTED,
        UNKNOWN
    }

    internal data class Feedback(
        val category: Category,
        val title: String,
        val detail: String
    )

    // These exact codes are currently produced by GatewayClient for non-2xx
    // responses. Don't parse arbitrary exception text or any server body.
    private val httpFailure = Regex("^gateway_http_([45][0-9]{2})$")

    fun describe(error: Throwable): Feedback {
        val statusCode = if (error.javaClass == IOException::class.java) {
            error.message?.let { httpFailure.matchEntire(it)?.groupValues?.get(1)?.toIntOrNull() }
        } else {
            null
        }

        return when {
            statusCode == 401 || statusCode == 403 -> Feedback(
                Category.AUTHENTICATION,
                "VPS-koppeling controleren",
                "De gateway heeft deze aanvraag niet geaccepteerd. Controleer de koppeling."
            )
            statusCode == 429 -> Feedback(
                Category.RATE_LIMIT,
                "Even te veel verzoeken",
                "Probeer het later opnieuw."
            )
            statusCode in setOf(502, 503, 504) -> Feedback(
                Category.SERVICE_UNAVAILABLE,
                "VPS tijdelijk niet beschikbaar",
                "Probeer het later opnieuw."
            )
            statusCode != null -> Feedback(
                Category.GATEWAY_REJECTED,
                "VPS-aanvraag mislukt",
                "De gateway kon deze aanvraag niet verwerken."
            )
            error is SSLException -> Feedback(
                Category.TLS_FAILURE,
                "Veilige verbinding mislukt",
                "Controleer de VPS-koppeling voordat je opnieuw probeert."
            )
            error is SocketTimeoutException -> Feedback(
                Category.CONNECTION_TIMEOUT,
                "Geen antwoord van VPS",
                "Controleer je verbinding en probeer opnieuw."
            )
            error is UnknownHostException || error is ConnectException -> Feedback(
                Category.CONNECTION_UNAVAILABLE,
                "VPS niet bereikbaar",
                "Controleer je verbinding en probeer opnieuw."
            )
            else -> Feedback(
                Category.UNKNOWN,
                "Er ging iets mis",
                "Probeer opnieuw of open de Gemini-fallback."
            )
        }
    }
}
