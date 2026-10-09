package nl.zennay.raiseai

import java.io.IOException

internal object GatewayResponseFieldPolicy {
    private const val INVALID_SCHEMA = "gateway_response_invalid_schema"
    private const val MAX_TOKEN_CHARS = 256
    private const val MAX_ANSWER_CHARS = 4_096

    fun tokenOrDefault(value: Any?, defaultValue: String): String =
        when (value) {
            null -> defaultValue
            is String -> value.takeIf(::isCanonicalToken) ?: invalidSchema()
            else -> invalidSchema()
        }

    fun optionalToken(value: Any?): String? =
        when (value) {
            null -> null
            is String -> value.takeIf(::isCanonicalToken) ?: invalidSchema()
            else -> invalidSchema()
        }

    fun booleanOrDefault(value: Any?, defaultValue: Boolean): Boolean =
        when (value) {
            null -> defaultValue
            is Boolean -> value
            else -> invalidSchema()
        }

    fun optionalAnswer(value: Any?): String? =
        when (value) {
            null -> null
            is String -> when {
                value.isBlank() -> null
                value.length > MAX_ANSWER_CHARS -> invalidSchema()
                else -> value
            }
            else -> invalidSchema()
        }

    fun invalidSchema(): Nothing = throw IOException(INVALID_SCHEMA)

    private fun isCanonicalToken(value: String): Boolean =
        value.isNotEmpty() &&
            value.length <= MAX_TOKEN_CHARS &&
            value == value.trim() &&
            value.none { char ->
                char.isWhitespace() || char.code <= 0x1f || char.code == 0x7f
            }
}
