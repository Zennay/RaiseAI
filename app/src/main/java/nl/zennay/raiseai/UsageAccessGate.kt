package nl.zennay.raiseai

/**
 * Treats Usage Access as an optional reliability enhancement, never a prerequisite for launch.
 *
 * OEM AppOps implementations may throw while looking up a grant, and older devices may not
 * expose the service at all. An unreadable grant must choose the conservative session lock
 * rather than crash the accelerometer callback or the Watch settings screen.
 */
internal object UsageAccessGate {
    fun isAllowed(grantedMode: Int, readMode: () -> Int?): Boolean =
        try {
            readMode() == grantedMode
        } catch (_: RuntimeException) {
            false
        }

    /** A blank or absent foreground package is not evidence of a usable UsageStats answer. */
    fun verifiedForegroundPackage(raw: String?): String? =
        raw?.takeIf { it.isNotBlank() }
}
