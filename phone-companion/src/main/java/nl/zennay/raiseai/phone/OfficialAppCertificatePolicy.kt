package nl.zennay.raiseai.phone

import java.security.MessageDigest

/**
 * A package name is not an authenticity proof. Verify the DER-encoded signing certificate of the
 * *installed* package against a known-good, independently trusted publisher SHA-256.
 *
 * Never populate the trust anchor by reading the same installed package's own certificate.
 */
internal object OfficialAppCertificatePolicy {
    const val PACKAGE = "com.openai.chatgpt"
    private val SHA256_HEX = Regex("^[a-fA-F0-9]{64}$")

    fun matches(expected: String?, installedCertificates: List<ByteArray>?): Boolean {
        if (expected == null || !SHA256_HEX.matches(expected)) return false
        if (installedCertificates == null || installedCertificates.size != 1) return false
        val signingCertificate = installedCertificates.single()
        if (signingCertificate.isEmpty()) return false
        val expectedBytes = ByteArray(32)
        for (i in expectedBytes.indices) {
            val start = i * 2
            val value = expected.substring(start, start + 2).toIntOrNull(16) ?: return false
            expectedBytes[i] = value.toByte()
        }
        val actualBytes = MessageDigest.getInstance("SHA-256").digest(signingCertificate)
        return MessageDigest.isEqual(expectedBytes, actualBytes)
    }
}
