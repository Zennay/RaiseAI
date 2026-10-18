package nl.zennay.raiseai

internal enum class HomeLaunchTarget {
    INSTALLED_APP,
    PLAY_STORE,
    WEB_STORE
}

internal object HomeLaunchPolicy {
    fun orderedTargets(installedAppAvailable: Boolean): List<HomeLaunchTarget> = buildList {
        if (installedAppAvailable) add(HomeLaunchTarget.INSTALLED_APP)
        add(HomeLaunchTarget.PLAY_STORE)
        add(HomeLaunchTarget.WEB_STORE)
    }
}
