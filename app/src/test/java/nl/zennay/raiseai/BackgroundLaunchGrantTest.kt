package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BackgroundLaunchGrantTest {
    @Test
    fun returnsTrueWhenPlatformGrantIsAvailable() {
        assertTrue(BackgroundLaunchGrant.isGranted { true })
    }

    @Test
    fun returnsFalseWhenPlatformGrantIsMissing() {
        assertFalse(BackgroundLaunchGrant.isGranted { false })
    }

    @Test
    fun platformReadFailureFailsClosed() {
        assertFalse(
            BackgroundLaunchGrant.isGranted {
                throw SecurityException("settings unavailable")
            }
        )
    }
}
