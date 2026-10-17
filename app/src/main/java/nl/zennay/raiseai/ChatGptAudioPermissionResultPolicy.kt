package nl.zennay.raiseai

/**
 * Android permission results are positional. A successful result for an
 * unrelated permission must never grant Gecko microphone access.
 *
 * This policy does not depend on Android classes, so malformed and cancelled
 * callbacks can be tested by the JVM without a physical Watch.
 */
internal object ChatGptAudioPermissionResultPolicy {
    enum class Decision { IGNORE_UNRELATED_REQUEST, GRANT, REJECT }

    fun decide(
        requestCode: Int,
        expectedRequestCode: Int,
        permissions: List<String>,
        grantResults: List<Int>,
        recordAudioPermission: String,
        permissionGranted: Int
    ): Decision {
        if (requestCode != expectedRequestCode) return Decision.IGNORE_UNRELATED_REQUEST

        // Raise AI requests exactly RECORD_AUDIO. Never turn an ambiguous,
        // reordered, empty or partial callback into a Gecko microphone grant.
        if (permissions.size != 1 || grantResults.size != 1 ||
            permissions[0] != recordAudioPermission
        ) return Decision.REJECT

        return if (grantResults[0] == permissionGranted) Decision.GRANT else Decision.REJECT
    }
}
