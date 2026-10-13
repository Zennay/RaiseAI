package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class GatewaySettingsPolicyTest {
    private val validToken = "s".repeat(40)

    @Test fun acceptsCanonicalHttpsOrigin() {
        val settings = GatewaySettingsPolicy.parse(" https://gateway.example/ ", validToken, null)
        assertEquals("https://gateway.example", settings?.baseUrl)
        assertEquals(validToken, settings?.token)
        assertNull(settings?.spkiSha256)
    }

    @Test fun acceptsExplicitHttpsPort() {
        assertEquals(
            "https://gateway.example:8443",
            GatewaySettingsPolicy.parse("https://gateway.example:8443", validToken, "")?.baseUrl
        )
    }

    @Test fun keepsValidatedSpkiPin() {
        val settings = GatewaySettingsPolicy.parse(
            "https://gateway.example", validToken, (1..32).joinToString(":") { "AB" }
        )
        assertEquals("ab".repeat(32), settings?.spkiSha256)
    }

    @Test fun rejectsInvalidPinInsteadOfIgnoringIt() {
        assertNull(GatewaySettingsPolicy.parse("https://gateway.example", validToken, "invalid"))
    }

    @Test fun rejectsHiddenControlCharactersInTlsPin() {
        val validPin = "ab".repeat(32)
        for (candidate in listOf(
            "\\t$validPin",
            "$validPin\\r",
            "${validPin.take(16)}\\n${validPin.drop(16)}",
            "$validPin\\u007f"
        )) {
            assertNull(GatewaySettingsPolicy.parse("https://gateway.example", validToken, candidate))
        }
    }

    @Test fun rejectsNonHttpsOrMissingHost() {
        for (url in listOf("http://gateway.example", "https:", "https://", "https:///x", "ftp://gateway.example")) {
            assertNull("accepted ${url}", GatewaySettingsPolicy.parse(url, validToken, null))
        }
    }

    @Test fun rejectsUserInfoAndLookalikeHost() {
        for (url in listOf(
            "https://user@gateway.example",
            "https://user:password@gateway.example",
            "https://gateway.example@evil.example",
            "https://gateway.example\\@evil.example"
        )) {
            assertNull("accepted ${url}", GatewaySettingsPolicy.parse(url, validToken, null))
        }
    }

    @Test fun rejectsNonRootPathsAndEncodedRootEscapes() {
        for (url in listOf(
            "https://gateway.example/api",
            "https://gateway.example//",
            "https://gateway.example/./",
            "https://gateway.example/%2e",
            "https://gateway.example/%2f",
            "https://gateway.example/..%2fendpoint"
        )) {
            assertNull("accepted ${url}", GatewaySettingsPolicy.parse(url, validToken, null))
        }
    }

    @Test fun rejectsQueryAndFragmentEvenOnRoot() {
        for (url in listOf(
            "https://gateway.example?next=evil",
            "https://gateway.example/#fragment",
            "https://gateway.example/?q=1",
            "https://gateway.example#fragment"
        )) {
            assertNull("accepted ${url}", GatewaySettingsPolicy.parse(url, validToken, null))
        }
    }

    @Test fun rejectsInvalidPorts() {
        for (url in listOf(
            "https://gateway.example:0",
            "https://gateway.example:65536",
            "https://gateway.example:-1",
            "https://gateway.example:abc"
        )) {
            assertNull("accepted ${url}", GatewaySettingsPolicy.parse(url, validToken, null))
        }
    }

    @Test fun rejectsControlCharactersInOrigin() {
        assertNull(GatewaySettingsPolicy.parse("https://gateway.example\n", validToken, null))
        assertNull(GatewaySettingsPolicy.parse("https://gateway.example\rhost", validToken, null))
    }

    @Test fun rejectsMissingOrShortTokens() {
        assertNull(GatewaySettingsPolicy.parse("https://gateway.example", null, null))
        assertNull(GatewaySettingsPolicy.parse("https://gateway.example", " ", null))
        assertNull(GatewaySettingsPolicy.parse("https://gateway.example", "a".repeat(31), null))
    }

    @Test fun rejectsTokensWithEmbeddedWhitespaceOrControls() {
        for (token in listOf(
            "a".repeat(32) + "\nb",
            "a".repeat(32) + "\tb",
            "a".repeat(32) + " b",
            "a".repeat(32) + "\u0000b"
        )) {
            assertNull(GatewaySettingsPolicy.parse("https://gateway.example", token, null))
        }
    }

    @Test fun rejectsOversizedOriginsAndTokens() {
        assertNull(GatewaySettingsPolicy.parse("https://" + "a".repeat(2_100) + ".example", validToken, null))
        assertNull(GatewaySettingsPolicy.parse("https://gateway.example", "a".repeat(4_097), null))
        assertEquals(4_096, GatewaySettingsPolicy.parse(
            "https://gateway.example", "a".repeat(4_096), null
        )?.token?.length)
    }

    @Test fun acceptsPrintableLegacyGatewayTokenSymbols() {
        val token = "Ab_-.+~/@;:?!=".repeat(3)
        assertEquals(token, GatewaySettingsPolicy.parse(
            "https://gateway.example", token, null
        )?.token)
    }

    @Test fun rejectsNonPrintableOrNonAsciiTokenCharacters() {
        for (token in listOf(
            "a".repeat(32) + "\u007f",
            "a".repeat(32) + "ö",
            "a".repeat(32) + "\u200B"
        )) {
            assertNull(GatewaySettingsPolicy.parse("https://gateway.example", token, null))
        }
    }

    @Test fun trimsTokenEdgesWithoutChangingValidToken() {
        val settings = GatewaySettingsPolicy.parse("https://gateway.example", "  $validToken  ", null)
        assertEquals(validToken, settings?.token)
    }

    @Test fun malformedOrNullUrlFailsClosed() {
        assertNull(GatewaySettingsPolicy.parse(null, validToken, null))
        assertNull(GatewaySettingsPolicy.parse(" ", validToken, null))
        assertNull(GatewaySettingsPolicy.parse("https://[invalid", validToken, null))
    }
}
