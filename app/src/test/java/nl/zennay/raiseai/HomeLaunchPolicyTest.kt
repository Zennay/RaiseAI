package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class HomeLaunchPolicyTest {
    @Test
    fun allAvailableRoutesKeepStrongestFirst() {
        assertEquals(
            listOf(
                HomeLaunchTarget.INSTALLED_APP,
                HomeLaunchTarget.PLAY_STORE,
                HomeLaunchTarget.WEB_STORE
            ),
            HomeLaunchPolicy.orderedAvailableTargets(
                installedAppAvailable = true,
                playStoreAvailable = true,
                webStoreAvailable = true
            )
        )
    }

    @Test
    fun storeFallbacksRemainAvailableWhenHomeIsNotInstalled() {
        assertEquals(
            listOf(
                HomeLaunchTarget.PLAY_STORE,
                HomeLaunchTarget.WEB_STORE
            ),
            HomeLaunchPolicy.orderedAvailableTargets(
                installedAppAvailable = false,
                playStoreAvailable = true,
                webStoreAvailable = true
            )
        )
    }

    @Test
    fun webStoreSurvivesMissingWearStoreScheme() {
        assertEquals(
            listOf(HomeLaunchTarget.WEB_STORE),
            HomeLaunchPolicy.orderedAvailableTargets(
                installedAppAvailable = false,
                playStoreAvailable = false,
                webStoreAvailable = true
            )
        )
    }

    @Test
    fun noResolvableTargetFailsClosed() {
        assertEquals(
            emptyList<HomeLaunchTarget>(),
            HomeLaunchPolicy.orderedAvailableTargets(
                installedAppAvailable = false,
                playStoreAvailable = false,
                webStoreAvailable = false
            )
        )
    }
}
