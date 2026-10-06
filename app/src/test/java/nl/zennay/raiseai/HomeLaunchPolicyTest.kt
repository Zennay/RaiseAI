package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class HomeLaunchPolicyTest {
    @Test
    fun installedAppWinsOverStoreFallbacks() {
        assertEquals(
            HomeLaunchTarget.INSTALLED_APP,
            HomeLaunchPolicy.choose(
                installedAppAvailable = true,
                playStoreAvailable = true,
                webStoreAvailable = true
            )
        )
    }

    @Test
    fun playStoreIsPreferredWhenHomeIsNotInstalled() {
        assertEquals(
            HomeLaunchTarget.PLAY_STORE,
            HomeLaunchPolicy.choose(
                installedAppAvailable = false,
                playStoreAvailable = true,
                webStoreAvailable = true
            )
        )
    }

    @Test
    fun webStoreIsUsedWhenWearStoreSchemeIsUnavailable() {
        assertEquals(
            HomeLaunchTarget.WEB_STORE,
            HomeLaunchPolicy.choose(
                installedAppAvailable = false,
                playStoreAvailable = false,
                webStoreAvailable = true
            )
        )
    }

    @Test
    fun noResolvableTargetFailsClosed() {
        assertEquals(
            HomeLaunchTarget.UNAVAILABLE,
            HomeLaunchPolicy.choose(
                installedAppAvailable = false,
                playStoreAvailable = false,
                webStoreAvailable = false
            )
        )
    }
}
