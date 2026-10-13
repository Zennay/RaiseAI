package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class ChatGptAudioPermissionResultPolicyTest {
    private fun decide(
        requestCode: Int = 808,
        permissions: List<String> = listOf(AUDIO),
        results: List<Int> = listOf(GRANTED)
    ) = ChatGptAudioPermissionResultPolicy.decide(
        requestCode = requestCode,
        expectedRequestCode = 808,
        permissions = permissions,
        grantResults = results,
        recordAudioPermission = AUDIO,
        permissionGranted = GRANTED
    )

    @Test
    fun matchingRecordAudioGrantIsAccepted() {
        assertEquals(ChatGptAudioPermissionResultPolicy.Decision.GRANT, decide())
    }

    @Test
    fun matchingDenialNeverStartsGeckoMicrophone() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.REJECT,
            decide(results = listOf(-1))
        )
    }

    @Test
    fun unrelatedRequestMustNotConsumePendingGeckoPermission() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.IGNORE_UNRELATED_REQUEST,
            decide(requestCode = 809)
        )
    }

    @Test
    fun matchingCodeButDifferentGrantedPermissionIsRejected() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.REJECT,
            decide(permissions = listOf("android.permission.POST_NOTIFICATIONS"))
        )
    }

    @Test
    fun matchingCodeWithoutPermissionsIsRejected() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.REJECT,
            decide(permissions = emptyList(), results = emptyList())
        )
    }

    @Test
    fun cancelledCallbackWithoutResultsIsRejected() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.REJECT,
            decide(results = emptyList())
        )
    }

    @Test
    fun mismatchedResultCountIsRejected() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.REJECT,
            decide(permissions = listOf(AUDIO, "other"), results = listOf(GRANTED))
        )
    }

    @Test
    fun extraPermissionFailsClosedEvenWhenAudioGranted() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.REJECT,
            decide(permissions = listOf(AUDIO, "other"), results = listOf(GRANTED, GRANTED))
        )
    }

    @Test
    fun reorderedAudioPermissionIsNeverConfusedWithOtherGrant() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.REJECT,
            decide(permissions = listOf("other", AUDIO), results = listOf(GRANTED, -1))
        )
    }

    @Test
    fun unknownGrantCodeIsRejected() {
        assertEquals(
            ChatGptAudioPermissionResultPolicy.Decision.REJECT,
            decide(results = listOf(123456))
        )
    }

    @Test
    fun unrelatedCallbackAlwaysIgnoredRegardlessOfMalformedContents() {
        for (code in listOf(-1, 0, 807, 809, Int.MAX_VALUE)) {
            assertEquals(
                ChatGptAudioPermissionResultPolicy.Decision.IGNORE_UNRELATED_REQUEST,
                decide(requestCode = code, permissions = listOf("other"), results = listOf(GRANTED))
            )
        }
    }

    companion object {
        private const val AUDIO = "android.permission.RECORD_AUDIO"
        private const val GRANTED = 0
    }
}
