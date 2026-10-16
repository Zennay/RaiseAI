package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test
import nl.zennay.raiseai.OfficialChatGptPhoneHandoffPolicy.Decision as D

class OfficialChatGptPhoneHandoffPolicyTest {
    private val policy = OfficialChatGptPhoneHandoffPolicy()
    private val now = 1_800_000_000_000L

    private fun request(
        id: String = "0123456789abcdef0123456789abcdef",
        issued: Long = now,
        action: String = OfficialChatGptPhoneHandoffPolicy.OPEN_APP_ACTION,
        version: Int = 1
    ) = OfficialChatGptPhoneHandoffPolicy.Request(version, action, id, issued)

    private fun decide(
        request: OfficialChatGptPhoneHandoffPolicy.Request? = request(),
        trusted: Boolean = true,
        consent: Boolean = true,
        verified: Boolean = true,
        at: Long = now
    ) = policy.decide(request, trusted, consent, verified, at)


    @Test fun acceptsOneFreshAuthorizedLauncherRequest() {
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
    }

    @Test fun duplicateRequestCannotLaunchTwice() {
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
        assertEquals(D.REPLAYED, decide())
    }

    @Test fun untrustedWearNodeIsRejectedEvenWithConsent() {
        assertEquals(D.UNTRUSTED_SENDER, decide(trusted = false))
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
    }

    @Test fun phoneConsentIsMandatoryAndNotEncodedInPayload() {
        assertEquals(D.USER_CONSENT_REQUIRED, decide(consent = false))
        assertEquals(D.OPEN_OFFICIAL_APP, decide(consent = true))
    }

    @Test fun phoneMustVerifyOfficialPublisherSeparately() {
        assertEquals(D.OFFICIAL_APP_UNVERIFIED, decide(verified = false))
        assertEquals(D.OPEN_OFFICIAL_APP, decide(verified = true))
    }

    @Test fun refusesUnsupportedActionIncludingVoiceDeepLink() {
        assertEquals(D.INVALID_REQUEST, decide(request(action = "START_VOICE")))
        assertEquals(D.INVALID_REQUEST, decide(request(action = "READ_ACCOUNT")))
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
    }

    @Test fun refusesWrongVersionAndNonOpaqueIdentifiers() {
        assertEquals(D.INVALID_REQUEST, decide(request(version = 2)))
        assertEquals(D.INVALID_REQUEST, decide(request(id = "../chatgpt")))
        assertEquals(D.INVALID_REQUEST, decide(request(id = "A".repeat(32))))
        assertEquals(D.INVALID_REQUEST, decide(request(id = "a".repeat(1000))))
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
    }

    @Test fun refusesMissingAndNonsensicalTimestamps() {
        assertEquals(D.INVALID_REQUEST, decide(null))
        assertEquals(D.INVALID_REQUEST, decide(request(issued = 0L)))
        assertEquals(D.INVALID_REQUEST, decide(at = 0L))
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
    }

    @Test fun ageDeadlineAndClockSkewAreExact() {
        assertEquals(D.OPEN_OFFICIAL_APP, decide(request(issued = now - 15_000L)))
        val fresh = OfficialChatGptPhoneHandoffPolicy()
        assertEquals(D.EXPIRED_OR_CLOCK_SKEW,
            fresh.decide(request(issued = now - 15_001L), true, true, true, now))
        assertEquals(D.EXPIRED_OR_CLOCK_SKEW,
            fresh.decide(request(issued = now + 5_001L), true, true, true, now))
        assertEquals(D.OPEN_OFFICIAL_APP,
            fresh.decide(request(issued = now + 5_000L), true, true, true, now))
    }

    @Test fun wallClockRollbackAfterAcceptFailsClosed() {
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
        assertEquals(D.EXPIRED_OR_CLOCK_SKEW,
            decide(request(id = "abcdef0123456789abcdef0123456789"), at = now - 1L))
        assertEquals(D.OPEN_OFFICIAL_APP,
            decide(request(id = "abcdef0123456789abcdef0123456789"), at = now + 3_000L))
    }

    @Test fun distinctRequestsCannotFloodThePublicAppLauncher() {
        val next = request(id = "abcdef0123456789abcdef0123456789")
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
        assertEquals(D.TOO_FREQUENT, decide(next, at = now))
        assertEquals(D.TOO_FREQUENT, decide(next, at = now + 2_999L))
        assertEquals(D.OPEN_OFFICIAL_APP, decide(next, at = now + 3_000L))
        assertEquals(D.REPLAYED, decide(next, at = now + 3_000L))
    }

    @Test fun cacheRefusesOverflowInsteadOfEvictingValidReplayGuards() {
        val short = OfficialChatGptPhoneHandoffPolicy(replayCapacity = 1)
        assertEquals(D.OPEN_OFFICIAL_APP, short.decide(request(), true, true, true, now))
        assertEquals(D.REPLAY_CACHE_FULL, short.decide(
            request(id = "abcdef0123456789abcdef0123456789"), true, true, true, now))
        assertEquals(D.REPLAYED, short.decide(request(), true, true, true, now))
    }

    @Test fun expiredReplayEntriesMayBePurgedWithoutExtendingOtherRequests() {
        assertEquals(D.OPEN_OFFICIAL_APP, decide())
        val later = now + 20_001L
        val next = request(id = "abcdef0123456789abcdef0123456789", issued = later)
        assertEquals(D.OPEN_OFFICIAL_APP, decide(next, at = later))
        assertEquals(D.REPLAYED, decide(next, at = later))
        assertEquals(D.EXPIRED_OR_CLOCK_SKEW, decide(request(), at = later))
    }

    @Test fun invalidClockNearLongMaxDoesNotWrapIntoValidRequest() {
        val fresh = OfficialChatGptPhoneHandoffPolicy()
        assertEquals(D.EXPIRED_OR_CLOCK_SKEW, fresh.decide(
            request(issued = 1L), true, true, true, Long.MAX_VALUE))
        assertEquals(D.EXPIRED_OR_CLOCK_SKEW, fresh.decide(
            request(issued = Long.MAX_VALUE), true, true, true, 1L))
    }
}
