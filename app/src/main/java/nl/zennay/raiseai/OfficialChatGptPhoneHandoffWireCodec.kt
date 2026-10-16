package nl.zennay.raiseai

/**
 * Minimal, canonical Watch -> phone command envelope. No credentials, audio, URLs, arbitrary
 * intents or user-provided text can be represented in the version-1 protocol.
 *
 * The bytes are not authentication: Android Wear transport must independently attest sender
 * identity and the phone must obtain its own consent and official-app verification.
 */
internal object OfficialChatGptPhoneHandoffWireCodec {
    private const val PREFIX = "r1"
    internal const val MAX_PACKET_BYTES = 96
    private val REQUEST_ID = Regex("^[0-9a-f]{32}$")
    private val POSITIVE_DECIMAL = Regex("^[1-9][0-9]{0,18}$")

    fun encode(request: OfficialChatGptPhoneHandoffPolicy.Request): ByteArray {
        require(request.version == OfficialChatGptPhoneHandoffPolicy.VERSION)
        require(request.action == OfficialChatGptPhoneHandoffPolicy.OPEN_APP_ACTION)
        require(REQUEST_ID.matches(request.requestId))
        require(request.issuedAtEpochMs > 0L)

        val packet = listOf(
            PREFIX,
            OfficialChatGptPhoneHandoffPolicy.OPEN_APP_ACTION,
            request.requestId,
            request.issuedAtEpochMs.toString()
        ).joinToString("|").toByteArray(Charsets.US_ASCII)
        check(packet.size <= MAX_PACKET_BYTES)
        return packet
    }

    fun decode(bytes: ByteArray?): OfficialChatGptPhoneHandoffPolicy.Request? {
        if (bytes == null || bytes.isEmpty() || bytes.size > MAX_PACKET_BYTES) return null
        // No UTF-8 replacement, invisible characters or trailing newline ambiguity.
        if (bytes.any { val v = it.toInt() and 0xff; v < 33 || v > 126 }) return null

        val parts = bytes.toString(Charsets.US_ASCII).split('|')
        if (parts.size != 4 ||
            parts[0] != PREFIX ||
            parts[1] != OfficialChatGptPhoneHandoffPolicy.OPEN_APP_ACTION ||
            !REQUEST_ID.matches(parts[2]) ||
            !POSITIVE_DECIMAL.matches(parts[3])
        ) return null

        val timeMs = parts[3].toLongOrNull() ?: return null
        return OfficialChatGptPhoneHandoffPolicy.Request(
            version = OfficialChatGptPhoneHandoffPolicy.VERSION,
            action = OfficialChatGptPhoneHandoffPolicy.OPEN_APP_ACTION,
            requestId = parts[2],
            issuedAtEpochMs = timeMs
        )
    }
}
