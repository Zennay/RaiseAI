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
    fun missingStringUsesDefault() {
        assertEquals(
            "unknown",
            GatewayResponseFieldPolicy.stringOrDefault(null, "unknown")
        )
    }

    @Test
    fun stringValueIsPreserved() {
        assertEquals(
            "quick_ai",
            GatewayResponseFieldPolicy.stringOrDefault("quick_ai", "unknown")
        )
    }

    @Test
    fun nonStringValueIsRejected() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseFieldPolicy.stringOrDefault(123, "unknown")
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
    fun optionalStringNormalizesMissingAndBlankValues() {
        assertNull(GatewayResponseFieldPolicy.optionalNonBlankString(null))
        assertNull(GatewayResponseFieldPolicy.optionalNonBlankString("   "))
        assertEquals(
            "antwoord",
            GatewayResponseFieldPolicy.optionalNonBlankString("antwoord")
        )
    }

    @Test
    fun optionalNonStringValueIsRejected() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseFieldPolicy.optionalNonBlankString(42)
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
