package nl.zennay.raiseai

/**
 * Pure decision boundary for the asynchronous Android microphone-permission callback.
 *
 * A callback for another request must never be treated as microphone denial. Likewise, a
 * granted permission in the first slot must not authorize recording when RECORD_AUDIO was
 * absent, denied, or the callback arrays are inconsistent.
 *
 * Deliberately Android-free so all decision paths can be exercised on the JVM.
 */
internal object NativeAudioPermissionResultPolicy {
    private const val RECORD_AUDIO = "android.permission.RECORD_AUDIO"
    private const val PERMISSION_GRANTED = 0

    enum class Action {
        IGNORE_UNRELATED_REQUEST,
        START_LISTENING,
        SHOW_PERMISSION_REQUIRED
    }

    fun decide(
        requestCode: Int,
        expectedAudioRequestCode: Int,
        permissions: List<String>,
        grantResults: List<Int>
    ): Action {
        if (requestCode != expectedAudioRequestCode) return Action.IGNORE_UNRELATED_REQUEST

        // Android can deliver an empty result on cancellation. Do not infer success from
        // an unrelated granted permission, repeated entries, or partial callback arrays.
        if (permissions.isEmpty() || permissions.size != grantResults.size ||
            permissions.count { it == RECORD_AUDIO } != 1
        ) {
            return Action.SHOW_PERMISSION_REQUIRED
        }

        val audioIndex = permissions.indexOf(RECORD_AUDIO)
        return if (grantResults[audioIndex] == PERMISSION_GRANTED) {
            Action.START_LISTENING
        } else {
            Action.SHOW_PERMISSION_REQUIRED
        }
    }
}
