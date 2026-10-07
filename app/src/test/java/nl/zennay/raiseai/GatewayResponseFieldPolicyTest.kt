package nl.zennay.raiseai

import java.io.IOException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class GatewayResponseFieldPolicyTest {
    @Test
    fun missingTokenUsesDefault() {
        assertEquals(
            "unknown",
            GatewayResponseFieldPolicy.tokenOrDefault(null, "unknown")
        )
    }

    @Test
    fun canonicalTokenIsPreserved() {
        assertEquals(
            "quick_ai",
            GatewayResponseFieldPolicy.tokenOrDefault("quick_ai", "unknown")
        )
    }

    @Test
    fun nonStringTokenIsRejected() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseFieldPolicy.tokenOrDefault(123, "unknown")
        }

        assertEquals("gateway_response_invalid_schema", error.message)
    }

    @Test
    fun malformedTokensAreRejected() {
        for (value in listOf("", " quick_ai", "quick ai", "quick_ai\n", "a".repeat(257))) {
            val error = assertThrows(IOException::class.java) {
                GatewayResponseFieldPolicy.tokenOrDefault(value, "unknown")
            }
            assertEquals("gateway_response_invalid_schema", error.message)
        }
    }

    @Test
    fun optionalTokenHandlesMissingAndCanonicalValues() {
        assertNull(GatewayResponseFieldPolicy.optionalToken(null))
        assertEquals(
            "connector_not_configured",
            GatewayResponseFieldPolicy.optionalToken("connector_not_configured")
        )
    }

    @Test
    fun optionalMalformedTokenIsRejected() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseFieldPolicy.optionalToken("bad reason")
        }

        assertEquals("gateway_response_invalid_schema", error.message)
    }

    @Test
    fun missingBooleanUsesDefault() {
        assertFalse(GatewayResponseFieldPolicy.booleanOrDefault(null, false))
    }

    @Test
    fun booleanValuesArePreserved() {
        assertTrue(GatewayResponseFieldPolicy.booleanOrDefault(true, false))
        assertFalse(GatewayResponseFieldPolicy.booleanOrDefault(false, true))
    }

    @Test
    fun stringBooleanIsRejected() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseFieldPolicy.booleanOrDefault("false", false)
        }

        assertEquals("gateway_response_invalid_schema", error.message)
    }

    @Test
    fun optionalAnswerNormalizesMissingAndBlankValues() {
        assertNull(GatewayResponseFieldPolicy.optionalAnswer(null))
        assertNull(GatewayResponseFieldPolicy.optionalAnswer("   "))
        assertEquals(
            "antwoord",
            GatewayResponseFieldPolicy.optionalAnswer("antwoord")
        )
    }

    @Test
    fun answerAtMaximumLengthIsAccepted() {
        val answer = "a".repeat(4_096)

        assertEquals(answer, GatewayResponseFieldPolicy.optionalAnswer(answer))
    }

    @Test
    fun oversizedAnswerIsRejected() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseFieldPolicy.optionalAnswer("a".repeat(4_097))
        }

        assertEquals("gateway_response_invalid_schema", error.message)
    }

    @Test
    fun optionalNonStringAnswerIsRejected() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseFieldPolicy.optionalAnswer(42)
        }

        assertEquals("gateway_response_invalid_schema", error.message)
    }

    @Test
    fun explicitInvalidSchemaUsesStableError() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseFieldPolicy.invalidSchema()
        }

        assertEquals("gateway_response_invalid_schema", error.message)
    }
}
