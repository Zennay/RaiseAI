package nl.zennay.raiseai

import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.X509TrustManager

object PinnedTls {
    fun normalizePin(raw: String): String? {
        val pin = raw
            .lowercase()
            .replace(":", "")
            .replace(" ", "")
            .trim()

        return pin.takeIf {
            it.length == 64 && it.all { char -> char in '0'..'9' || char in 'a'..'f' }
        }
    }

    fun socketFactory(expectedSpkiSha256: String): SSLSocketFactory {
        val expected = normalizePin(expectedSpkiSha256)
            ?: throw IllegalArgumentException("Invalid SPKI SHA-256 pin")

        val trustManager = object : X509TrustManager {
            override fun checkClientTrusted(
                chain: Array<out X509Certificate>?,
                authType: String?
            ) = Unit

            override fun checkServerTrusted(
                chain: Array<out X509Certificate>?,
                authType: String?
            ) {
                val leaf = chain?.firstOrNull()
                    ?: throw CertificateException("Missing server certificate")

                val nowMs = System.currentTimeMillis()
                if (!isCertificateCurrentlyValid(
                        notBeforeMs = leaf.notBefore.time,
                        notAfterMs = leaf.notAfter.time,
                        nowMs = nowMs
                    )
                ) {
                    throw CertificateException("Raise gateway certificate is not currently valid")
                }

                val actual = MessageDigest.getInstance("SHA-256")
                    .digest(leaf.publicKey.encoded)
                    .joinToString("") { "%02x".format(it) }

                if (!MessageDigest.isEqual(
                        actual.toByteArray(Charsets.US_ASCII),
                        expected.toByteArray(Charsets.US_ASCII)
                    )
                ) {
                    throw CertificateException("Raise gateway SPKI pin mismatch")
                }
            }

            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }

        return SSLContext.getInstance("TLS").apply {
            init(null, arrayOf(trustManager), SecureRandom())
        }.socketFactory
    }

    internal fun isCertificateCurrentlyValid(
        notBeforeMs: Long,
        notAfterMs: Long,
        nowMs: Long
    ): Boolean =
        notBeforeMs <= notAfterMs &&
            nowMs >= notBeforeMs &&
            nowMs <= notAfterMs

}