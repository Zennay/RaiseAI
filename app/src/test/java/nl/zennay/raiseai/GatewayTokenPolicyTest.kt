package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GatewayTokenPolicyTest {
    @Test
    fun acceptsLongVisibleToken() {
        assertTrue(GatewayTokenPolicy.isValid("abcdefghijklmnopqrstuvwxyz0123456789TOKEN"))
    }

    @Test
    fun rejectsShortToken() {
        assertFalse(GatewayTokenPolicy.isValid("too-short"))
    }

    @Test
    fun rejectsEmbeddedWhitespace() {
        assertFalse(
            GatewayTokenPolicy.isValid(
                "abcdefghijklmnopqrstuvwxyz0123456789 TOKEN"
            )
        )
        assertFalse(
            GatewayTokenPolicy.isValid(
                "abcdefghijklmnopqrstuvwxyz0123456789\tTOKEN"
            )
        )
    }

    @Test
    fun rejectsControlCharacters() {
        assertFalse(
            GatewayTokenPolicy.isValid(
                "abcdefghijklmnopqrstuvwxyz0123456789\u0000TOKEN"
            )
        )
    }
}
