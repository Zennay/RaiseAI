package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class NativeAudioPermissionResultPolicyTest {
    private val expectedCode = 201
    private val audio = "android.permission.RECORD_AUDIO"
    private val camera = "android.permission.CAMERA"
    private val grant = 0
    private val deny = -1

    private fun decide(
        requestCode: Int = expectedCode,
        permissions: List<String> = listOf(audio),
        results: List<Int> = listOf(grant)
    ) = NativeAudioPermissionResultPolicy.decide(
        requestCode, expectedCode, permissions, results
    )

    @Test
    fun matchingAudioGrantStartsListening() {
        assertEquals(NativeAudioPermissionResultPolicy.Action.START_LISTENING, decide())
    }

    @Test
    fun matchingAudioDenialShowsRecovery() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED,
            decide(results = listOf(deny))
        )
    }

    @Test
    fun unrelatedRequestDoesNotTurnIntoAnAudioError() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.IGNORE_UNRELATED_REQUEST,
            decide(requestCode = 99, permissions = emptyList(), results = emptyList())
        )
    }

    @Test
    fun cancelledPermissionPromptFailsClosed() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED,
            decide(permissions = emptyList(), results = emptyList())
        )
    }

    @Test
    fun grantedOtherPermissionCannotAuthorizeRecording() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED,
            decide(permissions = listOf(camera), results = listOf(grant))
        )
    }

    @Test
    fun matchingAudioPermissionMayAppearAfterAnotherGrant() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.START_LISTENING,
            decide(permissions = listOf(camera, audio), results = listOf(grant, grant))
        )
    }

    @Test
    fun firstGrantedPermissionDoesNotMaskAudioDenial() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED,
            decide(permissions = listOf(camera, audio), results = listOf(grant, deny))
        )
    }

    @Test
    fun missingGrantResultFailsClosed() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED,
            decide(permissions = listOf(audio, camera), results = listOf(grant))
        )
    }

    @Test
    fun extraGrantResultFailsClosed() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED,
            decide(permissions = listOf(audio), results = listOf(grant, grant))
        )
    }

    @Test
    fun duplicateAudioPermissionsAreAmbiguous() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED,
            decide(permissions = listOf(audio, audio), results = listOf(grant, grant))
        )
    }

    @Test
    fun arbitraryNonzeroPermissionResultCannotAuthorizeRecording() {
        assertEquals(
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED,
            decide(results = listOf(777))
        )
    }
}
