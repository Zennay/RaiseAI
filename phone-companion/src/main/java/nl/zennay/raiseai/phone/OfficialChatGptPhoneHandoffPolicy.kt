package nl.zennay.raiseai.phone

/**
 * Strict, platform-independent guard for a *future* trusted Wear -> Android-phone handoff.
 *
 * This authorises only a public Android launcher request. It does NOT activate ChatGPT Voice,
 * transfer microphone audio, attest an APK, authenticate a Wear node, or read ChatGPT data.
 * The phone-side caller must supply independently established transport identity, user consent
 * and cryptographic official-app verification. Never trust fields in a Watch message for those.
 *
 * One instance belongs to one paired transport session; the receiver must serialize calls.
 */
internal class OfficialChatGptPhoneHandoffPolicy(
    private val replayCapacity: Int = 512
) {
    internal data class Request(
        val version: Int,
        val action: String,
        val requestId: String,
        val issuedAtEpochMs: Long
    )

    internal enum class Decision {
        OPEN_OFFICIAL_APP,
        UNTRUSTED_SENDER,
        USER_CONSENT_REQUIRED,
        OFFICIAL_APP_UNVERIFIED,
        INVALID_REQUEST,
        EXPIRED_OR_CLOCK_SKEW,
        REPLAYED,
        TOO_FREQUENT,
        REPLAY_CACHE_FULL
    }

    private val seen = LinkedHashMap<String, Long>()
    private var lastAcceptedNowMs = 0L

    /**
     * [trustedSender] must come from Android's authenticated same-account paired-node identity,
     * never a node ID asserted inside the untrusted request.
     * [verifiedOfficialApp] must be backed by package signature verification outside this class.
     *
     * All failures are fail-closed and do not trigger an app start. A successful decision
     * authorises only Intent ACTION_MAIN + CATEGORY_LAUNCHER to the verified official package.
     */
    @Synchronized
    fun decide(
        request: Request?,
        trustedSender: Boolean,
        userConsented: Boolean,
        verifiedOfficialApp: Boolean,
        nowEpochMs: Long
    ): Decision {
        if (!trustedSender) return Decision.UNTRUSTED_SENDER
        if (!userConsented) return Decision.USER_CONSENT_REQUIRED
        if (!verifiedOfficialApp) return Decision.OFFICIAL_APP_UNVERIFIED

        if (request == null ||
            request.version != VERSION ||
            request.action != OPEN_APP_ACTION ||
            !REQUEST_ID.matches(request.requestId) ||
            request.issuedAtEpochMs <= 0L ||
            nowEpochMs <= 0L
        ) return Decision.INVALID_REQUEST

        // A clock rollback must not make an old request appear valid again.
        if (lastAcceptedNowMs > nowEpochMs) return Decision.EXPIRED_OR_CLOCK_SKEW

        val age = nowEpochMs - request.issuedAtEpochMs
        // Both timestamps are positive: avoid overflow by comparing before subtraction.
        if (request.issuedAtEpochMs > nowEpochMs) {
            if (request.issuedAtEpochMs - nowEpochMs > FUTURE_SKEW_MS) {
                return Decision.EXPIRED_OR_CLOCK_SKEW
            }
        } else if (age > MAX_AGE_MS) {
            return Decision.EXPIRED_OR_CLOCK_SKEW
        }

        // Expiry is based on the trusted receiving clock, not on a user-controlled timestamp.
        val iterator = seen.entries.iterator()
        while (iterator.hasNext()) {
            val entry = iterator.next()
            if (nowEpochMs >= entry.value &&
                nowEpochMs - entry.value > MAX_AGE_MS + FUTURE_SKEW_MS
            ) iterator.remove()
        }
        if (seen.containsKey(request.requestId)) return Decision.REPLAYED
        // Distinct random IDs must not become an assistant-start flood when a Watch retries.
        // This is per paired receiver session, not a device-global launch quota.
        if (lastAcceptedNowMs > 0L && nowEpochMs - lastAcceptedNowMs < MIN_LAUNCH_INTERVAL_MS) {
            return Decision.TOO_FREQUENT
        }

        // Never evict an in-window request to make room for a replay.
        if (replayCapacity < 1 || seen.size >= replayCapacity) return Decision.REPLAY_CACHE_FULL
        seen[request.requestId] = nowEpochMs
        lastAcceptedNowMs = nowEpochMs
        return Decision.OPEN_OFFICIAL_APP
    }

    internal companion object {
        const val VERSION = 1
        const val OPEN_APP_ACTION = "OPEN_OFFICIAL_CHATGPT_APP"
        const val MIN_LAUNCH_INTERVAL_MS = 3_000L
        const val MAX_AGE_MS = 15_000L
        const val FUTURE_SKEW_MS = 5_000L
        private val REQUEST_ID = Regex("^[0-9a-f]{32}$")
    }
}
