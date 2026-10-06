package nl.zennay.raiseai

internal enum class HomeLaunchTarget {
    INSTALLED_APP,
    PLAY_STORE,
    WEB_STORE
}

internal object HomeLaunchPolicy {
    fun orderedAvailableTargets(
        installedAppAvailable: Boolean,
        playStoreAvailable: Boolean,
        webStoreAvailable: Boolean
    ): List<HomeLaunchTarget> = buildList {
        if (installedAppAvailable) add(HomeLaunchTarget.INSTALLED_APP)
        if (playStoreAvailable) add(HomeLaunchTarget.PLAY_STORE)
        if (webStoreAvailable) add(HomeLaunchTarget.WEB_STORE)
    }
}
