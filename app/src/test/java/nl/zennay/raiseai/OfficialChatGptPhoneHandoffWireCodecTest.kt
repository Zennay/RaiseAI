package nl.zennay.raiseai

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OfficialChatGptPhoneHandoffWireCodecTest {
    private val id = "0123456789abcdef0123456789abcdef"
    private val action = OfficialChatGptPhoneHandoffPolicy.OPEN_APP_ACTION
    private val request = OfficialChatGptPhoneHandoffPolicy.Request(1, action, id, 1_800_000_000_000L)

    private fun decode(packet: String) =
        OfficialChatGptPhoneHandoffWireCodec.decode(packet.toByteArray(Charsets.UTF_8))

    @Test fun roundTripIsCanonicalAndContainsNoAccountData() {
        val bytes = OfficialChatGptPhoneHandoffWireCodec.encode(request)
        assertTrue(bytes.size <= OfficialChatGptPhoneHandoffWireCodec.MAX_PACKET_BYTES)
        assertArrayEquals(
            "r1|$action|$id|1800000000000".toByteArray(Charsets.US_ASCII), bytes
        )
        assertEquals(request, OfficialChatGptPhoneHandoffWireCodec.decode(bytes))
    }

    @Test fun emptyAndOversizedPayloadsFailClosed() {
        assertNull(OfficialChatGptPhoneHandoffWireCodec.decode(null))
        assertNull(OfficialChatGptPhoneHandoffWireCodec.decode(byteArrayOf()))
        assertNull(OfficialChatGptPhoneHandoffWireCodec.decode(ByteArray(97) { 65 }))
    }

    @Test fun unexpectedCommandsAndExtraFieldsAreNotSupported() {
        assertNull(decode("r1|START_VOICE|$id|1800000000000"))
        assertNull(decode("r1|$action|$id|1800000000000|secret"))
        assertNull(decode("r2|$action|$id|1800000000000"))
        assertNull(decode("r1|$action|$id"))
    }

    @Test fun rejectInvisibleControlAndUtf8Payloads() {
        assertNull(decode("r1|$action|$id|1800000000000\n"))
        assertNull(decode("r1|$action|$id|1800000000000\u0000"))
        assertNull(decode("r1|$action|$id|1800000000000é"))
    }

    @Test fun rejectNonCanonicalOrOverflowedEpoch() {
        assertNull(decode("r1|$action|$id|01800000000000"))
        assertNull(decode("r1|$action|$id|0"))
        assertNull(decode("r1|$action|$id|-1"))
        assertNull(decode("r1|$action|$id|9223372036854775808"))
    }

    @Test fun rejectInvalidNonRandomLookingOrUppercaseRequestId() {
        assertNull(decode("r1|$action|../../id|1800000000000"))
        assertNull(decode("r1|$action|${id.uppercase()}|1800000000000"))
        assertNull(decode("r1|$action|0000000000000000000000000000000|1800000000000"))
    }

    @Test fun encoderRejectsUnapprovedActionsAndInvalidIdentity() {
        val broken = request.copy(action = "READ_CHATGPT_CONVERSATIONS")
        var refused = false
        try { OfficialChatGptPhoneHandoffWireCodec.encode(broken) }
        catch (_: IllegalArgumentException) { refused = true }
        assertTrue(refused)

        refused = false
        try { OfficialChatGptPhoneHandoffWireCodec.encode(request.copy(requestId = "id")) }
        catch (_: IllegalArgumentException) { refused = true }
        assertTrue(refused)
    }

    @Test fun decodedEnvelopeStillRequiresPhoneConsentAndSenderProof() {
        val decoded = OfficialChatGptPhoneHandoffWireCodec.decode(
            OfficialChatGptPhoneHandoffWireCodec.encode(request)
        )
        val policy = OfficialChatGptPhoneHandoffPolicy()
        assertEquals(OfficialChatGptPhoneHandoffPolicy.Decision.UNTRUSTED_SENDER,
            policy.decide(decoded, false, true, true, request.issuedAtEpochMs))
        assertEquals(OfficialChatGptPhoneHandoffPolicy.Decision.USER_CONSENT_REQUIRED,
            policy.decide(decoded, true, false, true, request.issuedAtEpochMs))
        assertEquals(OfficialChatGptPhoneHandoffPolicy.Decision.OPEN_OFFICIAL_APP,
            policy.decide(decoded, true, true, true, request.issuedAtEpochMs))
    }
}
