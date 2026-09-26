package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PinnedTlsTest {
    @Test
    fun normalizesColonSeparatedSha256Pin() {
        val raw = (1..32).joinToString(":") { "ab" }
        val expected = "ab".repeat(32)

        assertEquals(expected, PinnedTls.normalizePin(raw))
    }

    @Test
    fun rejectsMalformedPins() {
        assertNull(PinnedTls.normalizePin("abc"))
        assertNull(PinnedTls.normalizePin("z".repeat(64)))
    }
}