package nl.zennay.raiseai

import java.io.ByteArrayInputStream
import java.io.IOException
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
    fun nullResponseBodyIsEmpty() {
        assertEquals("", GatewayResponseBodyReader.read(null))
    }
}
