package nl.zennay.raiseai

import java.io.IOException

internal object GatewayResponseMetadataPolicy {
    private val JSON_CONTENT_TYPE =
        Regex(
            """^application/json(?:\s*;\s*charset\s*=\s*(?:utf-8|"utf-8"))?\s*$""",
            RegexOption.IGNORE_CASE
        )

    fun validateSuccessfulResponse(contentType: String?, contentLength: Long) {
        val normalizedContentType = contentType?.trim()
        if (normalizedContentType.isNullOrEmpty() ||
            !JSON_CONTENT_TYPE.matches(normalizedContentType)
        ) {
            throw IOException("gateway_response_invalid_content_type")
        }

        if (contentLength > GatewayResponseBodyReader.MAX_RESPONSE_BYTES) {
            throw IOException("gateway_response_too_large")
        }
    }
}
