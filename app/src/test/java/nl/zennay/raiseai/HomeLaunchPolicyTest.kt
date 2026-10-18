package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class HomeLaunchPolicyTest {
    @Test
    fun installedAppIsTriedBeforeStoreFallbacks() {
        assertEquals(
            listOf(
                HomeLaunchTarget.INSTALLED_APP,
                HomeLaunchTarget.PLAY_STORE,
                HomeLaunchTarget.WEB_STORE
            ),
            HomeLaunchPolicy.orderedTargets(installedAppAvailable = true)
        )
    }

    @Test
    fun missingHomeStillTriesBothStoreRoutes() {
        assertEquals(
            listOf(
                HomeLaunchTarget.PLAY_STORE,
                HomeLaunchTarget.WEB_STORE
            ),
            HomeLaunchPolicy.orderedTargets(installedAppAvailable = false)
        )
    }
}
