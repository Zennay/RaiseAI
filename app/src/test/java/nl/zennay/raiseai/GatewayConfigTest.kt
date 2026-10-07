package nl.zennay.raiseai

import java.util.Properties
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class GatewayConfigTest {
    private fun properties(vararg entries: Pair<String, String>) =
        Properties().apply {
            entries.forEach { (key, value) -> setProperty(key, value) }
        }

    @Test
    fun parsesAndNormalizesValidGatewaySettings() {
        val settings = GatewayConfig.parse(
            properties(
                "url" to "  https://raise.example.test///  ",
                "token" to "  aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  ",
            )
        )

        assertEquals(
            GatewaySettings(
                baseUrl = "https://raise.example.test",
                token = "a".repeat(32),
                spkiSha256 = null,
            ),
            settings,
        )
    }

    @Test
    fun normalizesOptionalSpkiPin() {
        val rawPin = (1..32).joinToString(":") { "AB" }
        val settings = GatewayConfig.parse(
            properties(
                "url" to "https://raise.example.test",
                "token" to "b".repeat(32),
                "spki_sha256" to rawPin,
            )
        )

        assertEquals("ab".repeat(32), settings?.spkiSha256)
    }

    @Test
    fun rejectsMissingRequiredValues() {
        assertNull(
            GatewayConfig.parse(
                properties("token" to "a".repeat(32))
            )
        )
        assertNull(
            GatewayConfig.parse(
                properties("url" to "https://raise.example.test")
            )
        )
    }

    @Test
    fun rejectsNonHttpsGateway() {
        assertNull(
            GatewayConfig.parse(
                properties(
                    "url" to "http://raise.example.test",
                    "token" to "a".repeat(32),
                )
            )
        )
    }

    @Test
    fun rejectsShortToken() {
        assertNull(
            GatewayConfig.parse(
                properties(
                    "url" to "https://raise.example.test",
                    "token" to "too-short",
                )
            )
        )
    }

    @Test
    fun rejectsMalformedSpkiPin() {
        assertNull(
            GatewayConfig.parse(
                properties(
                    "url" to "https://raise.example.test",
                    "token" to "a".repeat(32),
                    "spki_sha256" to "not-a-sha256-pin",
                )
            )
        )
    }
}
