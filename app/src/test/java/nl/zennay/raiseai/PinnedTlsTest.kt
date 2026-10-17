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

    @Test
    fun acceptsCertificateAtInclusiveValidityBoundaries() {
        assertEquals(
            true,
            PinnedTls.isCertificateCurrentlyValid(
                notBeforeMs = 1_000L,
                notAfterMs = 2_000L,
                nowMs = 1_000L
            )
        )
        assertEquals(
            true,
            PinnedTls.isCertificateCurrentlyValid(
                notBeforeMs = 1_000L,
                notAfterMs = 2_000L,
                nowMs = 2_000L
            )
        )
    }

    @Test
    fun rejectsCertificateOutsideValidityWindow() {
        assertEquals(
            false,
            PinnedTls.isCertificateCurrentlyValid(
                notBeforeMs = 1_000L,
                notAfterMs = 2_000L,
                nowMs = 999L
            )
        )
        assertEquals(
            false,
            PinnedTls.isCertificateCurrentlyValid(
                notBeforeMs = 1_000L,
                notAfterMs = 2_000L,
                nowMs = 2_001L
            )
        )
    }

    @Test
    fun rejectsInvertedCertificateValidityWindow() {
        assertEquals(
            false,
            PinnedTls.isCertificateCurrentlyValid(
                notBeforeMs = 2_000L,
                notAfterMs = 1_000L,
                nowMs = 1_500L
            )
        )
    }

}