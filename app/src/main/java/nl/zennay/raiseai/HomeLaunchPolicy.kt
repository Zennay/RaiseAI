package nl.zennay.raiseai

internal enum class HomeLaunchTarget {
    INSTALLED_APP,
    PLAY_STORE,
    WEB_STORE,
    UNAVAILABLE
}

internal object HomeLaunchPolicy {
    fun choose(
        installedAppAvailable: Boolean,
        playStoreAvailable: Boolean,
        webStoreAvailable: Boolean
    ): HomeLaunchTarget = when {
        installedAppAvailable -> HomeLaunchTarget.INSTALLED_APP
        playStoreAvailable -> HomeLaunchTarget.PLAY_STORE
        webStoreAvailable -> HomeLaunchTarget.WEB_STORE
        else -> HomeLaunchTarget.UNAVAILABLE
    }
}
