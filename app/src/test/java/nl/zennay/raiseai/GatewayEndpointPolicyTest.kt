package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class GatewayEndpointPolicyTest {
    @Test
    fun acceptsAndNormalizesHttpsOrigin() {
        assertEquals(
            "https://raise.example.invalid:8787",
            GatewayEndpointPolicy.normalize("  HTTPS://raise.example.invalid:8787/  ")
        )
    }

    @Test
    fun rejectsNonHttpsAndMissingHost() {
        assertNull(GatewayEndpointPolicy.normalize("http://raise.example.invalid"))
        assertNull(GatewayEndpointPolicy.normalize("https://"))
        assertNull(GatewayEndpointPolicy.normalize(null))
    }

    @Test
    fun rejectsCredentialsQueryFragmentAndPath() {
        assertNull(GatewayEndpointPolicy.normalize("https://user:pass@raise.example.invalid"))
        assertNull(GatewayEndpointPolicy.normalize("https://raise.example.invalid/?token=secret"))
        assertNull(GatewayEndpointPolicy.normalize("https://raise.example.invalid/#debug"))
        assertNull(GatewayEndpointPolicy.normalize("https://raise.example.invalid/api"))
    }

    @Test
    fun rejectsInvalidPortsAndMalformedUris() {
        assertNull(GatewayEndpointPolicy.normalize("https://raise.example.invalid:0"))
        assertNull(GatewayEndpointPolicy.normalize("https://raise.example.invalid:70000"))
        assertNull(GatewayEndpointPolicy.normalize("https://raise example.invalid"))
    }

    @Test
    fun preservesExplicitValidPort() {
        assertEquals(
            "https://127.0.0.1:8787",
            GatewayEndpointPolicy.normalize("https://127.0.0.1:8787")
        )
    }
}
