package nl.zennay.raiseai

internal object GatewayTokenPolicy {
    private const val MIN_TOKEN_LENGTH = 32

    fun isValid(token: String): Boolean =
        token.length >= MIN_TOKEN_LENGTH &&
            token.none { it.isWhitespace() || it.isISOControl() }
}
