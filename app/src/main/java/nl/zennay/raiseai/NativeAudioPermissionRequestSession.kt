package nl.zennay.raiseai

/**
 * Tracks exactly one outstanding native microphone-permission prompt.
 *
 * An unrelated callback leaves the active request untouched. A matching callback
 * is consumed exactly once, even when the permission is denied or the returned
 * arrays are malformed. Activity teardown must call invalidate(), and the
 * Activity must begin the request *before* invoking Android requestPermissions.
 *
 * This protects against duplicate callbacks; it cannot by itself distinguish
 * Android callbacks from two separate Activity instances using the same code.
 */
internal class NativeAudioPermissionRequestSession(
    private val expectedAudioRequestCode: Int
) {
    private var pending = false

    fun beginRequest(): Boolean {
        if (pending) return false
        pending = true
        return true
    }

    fun onResult(
        requestCode: Int,
        permissions: List<String>,
        grantResults: List<Int>
    ): NativeAudioPermissionResultPolicy.Action {
        if (!pending || requestCode != expectedAudioRequestCode) {
            return NativeAudioPermissionResultPolicy.Action.IGNORE_UNRELATED_REQUEST
        }

        // Mark consumed before deciding so denial, cancellation and ambiguous
        // results cannot be replayed into a later listening attempt.
        pending = false
        return NativeAudioPermissionResultPolicy.decide(
            requestCode,
            expectedAudioRequestCode,
            permissions,
            grantResults
        )
    }

    fun invalidate() {
        pending = false
    }
}
