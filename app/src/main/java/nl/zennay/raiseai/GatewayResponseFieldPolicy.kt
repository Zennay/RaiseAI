package nl.zennay.raiseai

import java.io.IOException

internal object GatewayResponseFieldPolicy {
    private const val INVALID_SCHEMA = "gateway_response_invalid_schema"

    fun stringOrDefault(value: Any?, defaultValue: String): String =
        when (value) {
            null -> defaultValue
            is String -> value
            else -> throw IOException(INVALID_SCHEMA)
        }

    fun booleanOrDefault(value: Any?, defaultValue: Boolean): Boolean =
        when (value) {
            null -> defaultValue
            is Boolean -> value
            else -> throw IOException(INVALID_SCHEMA)
        }

    fun optionalNonBlankString(value: Any?): String? =
        when (value) {
            null -> null
            is String -> value.takeIf { it.isNotBlank() }
            else -> throw IOException(INVALID_SCHEMA)
        }

    fun invalidSchema(): Nothing = throw IOException(INVALID_SCHEMA)
}
