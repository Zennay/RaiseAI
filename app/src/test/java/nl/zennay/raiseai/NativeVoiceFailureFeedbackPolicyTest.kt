package nl.zennay.raiseai

import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLHandshakeException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeVoiceFailureFeedbackPolicyTest {
    private val policy = NativeVoiceFailureFeedbackPolicy

    @Test
    fun mapsKnownGatewayAuthenticationStatusesWithoutDisplayingRawStatus() {
        for (status in listOf(401, 403)) {
            val feedback = policy.describe(IOException("gateway_http_$status"))
            assertEquals(
                NativeVoiceFailureFeedbackPolicy.Category.AUTHENTICATION,
                feedback.category
            )
            assertEquals("VPS-koppeling controleren", feedback.title)
            assertFalse(feedback.detail.contains(status.toString()))
        }
    }

    @Test
    fun mapsRateLimitAndTemporaryOutageToActionableRetryLater() {
        assertEquals(
            NativeVoiceFailureFeedbackPolicy.Category.RATE_LIMIT,
            policy.describe(IOException("gateway_http_429")).category
        )
        for (status in listOf(502, 503, 504)) {
            val feedback = policy.describe(IOException("gateway_http_$status"))
            assertEquals(
                NativeVoiceFailureFeedbackPolicy.Category.SERVICE_UNAVAILABLE,
                feedback.category
            )
            assertTrue(feedback.detail.contains("later"))
        }
    }

    @Test
    fun nonSpecial4xxAnd5xxRemainGenericWithoutResponseDetails() {
        for (status in listOf(400, 404, 408, 418, 422, 500, 501, 599)) {
            assertEquals(
                NativeVoiceFailureFeedbackPolicy.Category.GATEWAY_REJECTED,
                policy.describe(IOException("gateway_http_$status")).category
            )
        }
    }

    @Test
    fun malformedOrSuccessfulHttpStatusCannotProduceTrustedGatewayFeedback() {
        for (message in listOf(
            "", "gateway_http_200", "gateway_http_301", "gateway_http_099",
            "gateway_http_401 extra", " gateway_http_401", "gateway_http_401\\n",
            "gateway_http_0401", "gateway_http_401?token=secret"
        )) {
            assertEquals(
                NativeVoiceFailureFeedbackPolicy.Category.UNKNOWN,
                policy.describe(IOException(message)).category
            )
        }
    }

    @Test
    fun timeoutAndTlsFailuresAreDistinctFromOrdinaryConnectivity() {
        assertEquals(
            NativeVoiceFailureFeedbackPolicy.Category.CONNECTION_TIMEOUT,
            policy.describe(SocketTimeoutException("timeout")).category
        )
        assertEquals(
            NativeVoiceFailureFeedbackPolicy.Category.TLS_FAILURE,
            policy.describe(SSLHandshakeException("pinned tls certificate mismatch")).category
        )
        for (error in listOf(
            UnknownHostException("private.internal"),
            ConnectException("Connection refused 192.168.1.9:8443")
        )) {
            assertEquals(
                NativeVoiceFailureFeedbackPolicy.Category.CONNECTION_UNAVAILABLE,
                policy.describe(error).category
            )
        }
    }

    @Test
    fun unknownExceptionsAlwaysHaveSafeFallbackInstructions() {
        for (error in listOf(
            IllegalArgumentException("Bearer secret-123"),
            IllegalStateException("https://private.example/api?token=abc"),
            NullPointerException("sensitive contact"),
            IOException("password=abcdef"),
            RuntimeException("customer-private-message")
        )) {
            val feedback = policy.describe(error)
            assertEquals(NativeVoiceFailureFeedbackPolicy.Category.UNKNOWN, feedback.category)
            assertTrue(feedback.detail.contains("Gemini-fallback"))
        }
    }

    @Test
    fun noExceptionDetailUrlCredentialOrCauseCanReachEitherDisplayField() {
        val secrets = listOf(
            "Bearer topsecret",
            "https://internal.example/gateway",
            "user@private.example",
            "Authorization: token",
            "password=redacted",
            "gateway_http_401?key=abc"
        )
        for (secret in secrets) {
            val error = IOException(secret, IllegalStateException("nested: $secret"))
            val feedback = policy.describe(error)
            val visible = feedback.title + " " + feedback.detail
            assertFalse(visible.contains(secret))
            assertFalse(visible.contains("topsecret"))
            assertFalse(visible.contains("private.example"))
            assertFalse(visible.contains("password"))
        }
    }

    @Test
    fun messageLookupOnArbitraryIOExceptionSubclassIsNeverRequired() {
        val tricky = object : IOException("private token") {
            override val message: String
                get() = throw IllegalStateException("message must not be read")
        }
        val feedback = policy.describe(tricky)
        assertEquals(NativeVoiceFailureFeedbackPolicy.Category.UNKNOWN, feedback.category)
    }

    @Test
    fun titlesAndDetailsAreBoundedNonBlankDutchCopy() {
        val errors = listOf(
            IOException("gateway_http_401"),
            IOException("gateway_http_429"),
            IOException("gateway_http_503"),
            IOException("gateway_http_500"),
            SSLHandshakeException("bad"),
            SocketTimeoutException("slow"),
            UnknownHostException("missing"),
            IllegalStateException("unknown")
        )
        for (error in errors) {
            val feedback = policy.describe(error)
            assertTrue(feedback.title.isNotBlank())
            assertTrue(feedback.detail.isNotBlank())
            assertTrue(feedback.title.length <= 65)
            assertTrue(feedback.detail.length <= 120)
            assertFalse(feedback.title.contains("\\n"))
            assertFalse(feedback.detail.contains("\\n"))
        }
    }
}
