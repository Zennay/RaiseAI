package nl.zennay.raiseai.phone

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.MessageDigest

class OfficialAppCertificatePolicyTest {
    private val certificate = "test-der-certificate".toByteArray()
    private val expected = MessageDigest.getInstance("SHA-256").digest(certificate)
        .joinToString("") { "%02x".format(it.toInt() and 0xff) }

    @Test fun singleMatchingPublisherCertificateIsAccepted() {
        assertTrue(OfficialAppCertificatePolicy.matches(expected, listOf(certificate)))
    }

    @Test fun uppercaseDigestMatchesSameCertificate() {
        assertTrue(OfficialAppCertificatePolicy.matches(expected.uppercase(), listOf(certificate)))
    }

    @Test fun wrongDigestFailsClosed() {
        assertFalse(OfficialAppCertificatePolicy.matches("f".repeat(64), listOf(certificate)))
    }

    @Test fun missingReferenceCannotClaimOfficialPublisher() {
        assertFalse(OfficialAppCertificatePolicy.matches(null, listOf(certificate)))
        assertFalse(OfficialAppCertificatePolicy.matches("", listOf(certificate)))
    }

    @Test fun malformedOrWhitespaceReferenceIsRejected() {
        for (value in listOf("abc", expected + " ", "0x" + expected, expected + "\n")) {
            assertFalse(OfficialAppCertificatePolicy.matches(value, listOf(certificate)))
        }
    }

    @Test fun missingOrMultipleSignersAreRejected() {
        assertFalse(OfficialAppCertificatePolicy.matches(expected, null))
        assertFalse(OfficialAppCertificatePolicy.matches(expected, emptyList()))
        assertFalse(OfficialAppCertificatePolicy.matches(expected, listOf(certificate, certificate)))
    }

    @Test fun noCertificateOrDifferentCertificateFails() {
        assertFalse(OfficialAppCertificatePolicy.matches(expected, listOf(byteArrayOf())))
        assertFalse(OfficialAppCertificatePolicy.matches(expected, listOf("attacker".toByteArray())))
    }
}
