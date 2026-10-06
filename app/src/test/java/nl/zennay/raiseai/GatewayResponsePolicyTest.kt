package nl.zennay.raiseai

import java.io.ByteArrayInputStream
import java.io.IOException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class GatewayResponsePolicyTest {

    @Test
    fun acceptsAndNormalizesAnsweredResponse() {
        val response = GatewayResponsePolicy.validate(
            route = " quick_ai ",
            status = " answered ",
            executionEnabled = true,
            executionReason = " ",
            answer = "  Hallo vanaf Raise AI.  "
        )

        assertEquals("quick_ai", response.route)
        assertEquals("answered", response.status)
        assertEquals(true, response.executionEnabled)
        assertNull(response.executionReason)
        assertEquals("Hallo vanaf Raise AI.", response.answer)
    }

    @Test
    fun acceptsRoutedResponseWithoutAnswer() {
        val response = GatewayResponsePolicy.validate(
            route = "zcloud_task",
            status = "routed",
            executionEnabled = false,
            executionReason = "connector_not_configured",
            answer = null
        )

        assertEquals("zcloud_task", response.route)
        assertEquals("routed", response.status)
        assertEquals(false, response.executionEnabled)
        assertEquals("connector_not_configured", response.executionReason)
        assertNull(response.answer)
    }

    @Test
    fun rejectsMissingRoute() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponsePolicy.validate(
                route = " ",
                status = "routed",
                executionEnabled = false,
                executionReason = null,
                answer = null
            )
        }

        assertEquals("gateway_response_missing_route", error.message)
    }

    @Test
    fun rejectsUnknownStatus() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponsePolicy.validate(
                route = "quick_ai",
                status = "done",
                executionEnabled = true,
                executionReason = null,
                answer = "ok"
            )
        }

        assertEquals("gateway_response_invalid_status", error.message)
    }

    @Test
    fun answeredStatusRequiresAnswer() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponsePolicy.validate(
                route = "quick_ai",
                status = "answered",
                executionEnabled = true,
                executionReason = null,
                answer = null
            )
        }

        assertEquals("gateway_response_missing_answer", error.message)
    }

    @Test
    fun routedStatusRejectsAmbiguousAnswer() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponsePolicy.validate(
                route = "quick_ai",
                status = "routed",
                executionEnabled = true,
                executionReason = null,
                answer = "unexpected"
            )
        }

        assertEquals("gateway_response_ambiguous_answer", error.message)
    }

    @Test
    fun boundedReaderAcceptsExactLimit() {
        val payload = "x".repeat(32)

        val actual = GatewayResponsePolicy.readUtf8Bounded(
            ByteArrayInputStream(payload.toByteArray()),
            maxBytes = 32
        )

        assertEquals(payload, actual)
    }

    @Test
    fun boundedReaderRejectsResponsePastLimit() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponsePolicy.readUtf8Bounded(
                ByteArrayInputStream("x".repeat(33).toByteArray()),
                maxBytes = 32
            )
        }

        assertEquals("gateway_response_too_large", error.message)
    }
}
