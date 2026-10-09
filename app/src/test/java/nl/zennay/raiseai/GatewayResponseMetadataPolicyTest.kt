package nl.zennay.raiseai

import java.io.IOException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class GatewayResponseMetadataPolicyTest {
    @Test
    fun acceptsCanonicalJsonMediaTypeAtExactBodyLimit() {
        GatewayResponseMetadataPolicy.validateSuccessfulResponse(
            "application/json",
            GatewayResponseBodyReader.MAX_RESPONSE_BYTES.toLong()
        )
    }

    @Test
    fun acceptsUtf8CharsetCaseInsensitively() {
        GatewayResponseMetadataPolicy.validateSuccessfulResponse(
            " Application/JSON; Charset=UTF-8 ",
            128L
        )
        GatewayResponseMetadataPolicy.validateSuccessfulResponse(
            "application/json; charset=\"utf-8\"",
            128L
        )
    }

    @Test
    fun acceptsUnknownContentLengthBecauseStreamLimitStillApplies() {
        GatewayResponseMetadataPolicy.validateSuccessfulResponse(
            "application/json; charset=utf-8",
            -1L
        )
    }

    @Test
    fun rejectsMissingContentType() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseMetadataPolicy.validateSuccessfulResponse(null, 12L)
        }

        assertEquals("gateway_response_invalid_content_type", error.message)
    }

    @Test
    fun rejectsNonJsonContentType() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseMetadataPolicy.validateSuccessfulResponse("text/html", 12L)
        }

        assertEquals("gateway_response_invalid_content_type", error.message)
    }

    @Test
    fun rejectsDeclaredSuccessBodyAboveLimitBeforeReading() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseMetadataPolicy.validateSuccessfulResponse(
                "application/json; charset=utf-8",
                GatewayResponseBodyReader.MAX_RESPONSE_BYTES.toLong() + 1L
            )
        }

        assertEquals("gateway_response_too_large", error.message)
    }

    @Test
    fun rejectsDeclaredErrorBodyAboveLimitBeforeReading() {
        val error = assertThrows(IOException::class.java) {
            GatewayResponseMetadataPolicy.validateBodyLength(
                GatewayResponseBodyReader.MAX_RESPONSE_BYTES.toLong() + 1L
            )
        }

        assertEquals("gateway_response_too_large", error.message)
    }
}
