package nl.zennay.raiseai

import java.io.ByteArrayInputStream
import java.io.IOException
import java.io.InputStream
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class GatewayResponseBodyReaderTest {
    @Test
    fun acceptsResponseAtExactByteLimit() {
        val payload = "a".repeat(GatewayResponseBodyReader.MAX_RESPONSE_BYTES)

        val result = GatewayResponseBodyReader.read(
            ByteArrayInputStream(payload.toByteArray(Charsets.UTF_8))
        )

        assertEquals(payload, result)
    }

    @Test
    fun rejectsResponseAboveByteLimit() {
        val payload = "a".repeat(GatewayResponseBodyReader.MAX_RESPONSE_BYTES + 1)

        val error = assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(
                ByteArrayInputStream(payload.toByteArray(Charsets.UTF_8))
            )
        }

        assertEquals("gateway_response_too_large", error.message)
    }

    @Test
    fun oversizedResponseClosesInputStream() {
        val payload = "a".repeat(GatewayResponseBodyReader.MAX_RESPONSE_BYTES + 1)
            .toByteArray(Charsets.UTF_8)
        var closed = false
        val stream = object : ByteArrayInputStream(payload) {
            override fun close() {
                closed = true
                super.close()
            }
        }

        assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(stream)
        }

        assertTrue(closed)
    }

    @Test
    fun limitCountsUtf8BytesInsteadOfCharacters() {
        val payload = "é".repeat(GatewayResponseBodyReader.MAX_RESPONSE_BYTES / 2 + 1)

        assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(
                ByteArrayInputStream(payload.toByteArray(Charsets.UTF_8))
            )
        }
    }

    @Test
    fun rejectsMalformedUtf8InsteadOfReplacingBytes() {
        val malformed = byteArrayOf(0xC3.toByte(), 0x28)

        val error = assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(ByteArrayInputStream(malformed))
        }

        assertEquals("gateway_response_invalid_utf8", error.message)
    }

    @Test
    fun malformedUtf8ClosesInputStream() {
        var closed = false
        val stream = object : ByteArrayInputStream(byteArrayOf(0xC3.toByte(), 0x28)) {
            override fun close() {
                closed = true
                super.close()
            }
        }

        assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(stream)
        }

        assertTrue(closed)
    }

    @Test
    fun zeroProgressReadFailsAndClosesStream() {
        var closed = false
        val stream = object : InputStream() {
            override fun read(): Int = 0

            override fun read(buffer: ByteArray, offset: Int, length: Int): Int = 0

            override fun close() {
                closed = true
            }
        }

        val error = assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(stream)
        }

        assertEquals("gateway_response_read_stalled", error.message)
        assertTrue(closed)
    }

    @Test
    fun acceptsBodyMatchingDeclaredLength() {
        val payload = """{"status":"answered"}""".toByteArray(Charsets.UTF_8)

        val result = GatewayResponseBodyReader.read(
            ByteArrayInputStream(payload),
            payload.size.toLong()
        )

        assertEquals(String(payload, Charsets.UTF_8), result)
    }

    @Test
    fun rejectsBodyShorterThanDeclaredLength() {
        val payload = "{}".toByteArray(Charsets.UTF_8)

        val error = assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(
                ByteArrayInputStream(payload),
                payload.size.toLong() + 1L
            )
        }

        assertEquals("gateway_response_length_mismatch", error.message)
    }

    @Test
    fun rejectsBodyLongerThanDeclaredLength() {
        val payload = "{}".toByteArray(Charsets.UTF_8)

        val error = assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(
                ByteArrayInputStream(payload),
                payload.size.toLong() - 1L
            )
        }

        assertEquals("gateway_response_length_mismatch", error.message)
    }

    @Test
    fun declaredNonEmptyBodyRejectsMissingStream() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseBodyReader.read(null, 1L)
        }

        assertEquals("gateway_response_length_mismatch", error.message)
    }

    @Test
    fun nullResponseBodyIsEmptyWhenLengthIsUnknown() {
        assertEquals("", GatewayResponseBodyReader.read(null))
    }
}
