package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeAudioPermissionRequestSessionTest {
    private val expectedCode = 201
    private val audio = "android.permission.RECORD_AUDIO"
    private val camera = "android.permission.CAMERA"
    private val allow = NativeAudioPermissionResultPolicy.Action.START_LISTENING
    private val deny = NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED
    private val ignore = NativeAudioPermissionResultPolicy.Action.IGNORE_UNRELATED_REQUEST

    private fun NativeAudioPermissionRequestSession.result(
        requestCode: Int = expectedCode,
        permissions: List<String> = listOf(audio),
        grants: List<Int> = listOf(0)
    ) = onResult(requestCode, permissions, grants)

    @Test fun unsolicitedGrantMustNotStartMicrophone() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        assertEquals(ignore, session.result())
    }

    @Test fun successfulPromptStartsOnlyOnce() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        assertTrue(session.beginRequest())
        assertEquals(allow, session.result())
        assertEquals(ignore, session.result())
    }

    @Test fun unrelatedRequestDoesNotConsumePendingAudioPrompt() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        assertTrue(session.beginRequest())
        assertEquals(ignore, session.result(requestCode = 999, permissions = listOf(camera)))
        assertFalse(session.beginRequest())
        assertEquals(allow, session.result())
    }

    @Test fun repeatedBeginCannotCreateASecondPendingPrompt() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        assertTrue(session.beginRequest())
        assertFalse(session.beginRequest())
        assertEquals(deny, session.result(grants = listOf(-1)))
        assertEquals(ignore, session.result(grants = listOf(0)))
    }

    @Test fun cancellationIsConsumedWithoutStartingMicrophone() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        session.beginRequest()
        assertEquals(deny, session.result(permissions = emptyList(), grants = emptyList()))
        assertEquals(ignore, session.result())
    }

    @Test fun malformedResultCannotLaterBeReplayedAsSuccess() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        session.beginRequest()
        assertEquals(deny, session.result(permissions = listOf(audio, camera), grants = listOf(0)))
        assertEquals(ignore, session.result())
    }

    @Test fun teardownInvalidatesOutstandingPrompt() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        session.beginRequest()
        session.invalidate()
        assertEquals(ignore, session.result())
        assertFalse(session.beginRequest())
    }

    @Test fun explicitNewPromptAfterTerminalCallbackIsPermitted() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        session.beginRequest()
        assertEquals(deny, session.result(grants = listOf(-1)))
        assertTrue(session.beginRequest())
        assertEquals(allow, session.result())
        assertEquals(ignore, session.result())
    }

    @Test fun invalidationIsTerminalAndIdempotent() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        session.beginRequest()
        session.invalidate()
        session.invalidate()
        assertEquals(ignore, session.result())
        assertFalse(session.beginRequest())
        assertEquals(ignore, session.result())
    }

    @Test fun alreadyConsumedGrantCannotBeReplayedAfterTeardown() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        session.beginRequest()
        assertEquals(allow, session.result())
        session.invalidate()
        assertFalse(session.beginRequest())
        assertEquals(ignore, session.result())
    }

    @Test fun invalidationBeforeAnyPromptPermanentlyRejectsPrompts() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        session.invalidate()
        assertFalse(session.beginRequest())
        assertEquals(ignore, session.result())
    }

    @Test fun unfamiliarGrantResultFailsClosedAndIsConsumed() {
        val session = NativeAudioPermissionRequestSession(expectedCode)
        session.beginRequest()
        assertEquals(deny, session.result(grants = listOf(9)))
        assertEquals(ignore, session.result())
    }
}
