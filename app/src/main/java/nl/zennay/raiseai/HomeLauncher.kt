package nl.zennay.raiseai

import android.app.Activity
import android.content.Intent
import android.net.Uri

object HomeLauncher {
    private const val HOME_PACKAGE = "com.google.android.apps.chromecast.app"
    private const val PLAY_STORE_WEB_BASE = "https://play.google.com/store/apps/details?id="

    fun open(activity: Activity): Boolean {
        val installedApp = activity.packageManager.getLaunchIntentForPackage(HOME_PACKAGE)
        val playStore = Intent(
            Intent.ACTION_VIEW,
            Uri.parse("market://details?id=$HOME_PACKAGE")
        )
        val webStore = Intent(
            Intent.ACTION_VIEW,
            Uri.parse("$PLAY_STORE_WEB_BASE$HOME_PACKAGE")
        )

        val intents = mapOf(
            HomeLaunchTarget.INSTALLED_APP to installedApp,
            HomeLaunchTarget.PLAY_STORE to playStore,
            HomeLaunchTarget.WEB_STORE to webStore
        )

        val candidates = HomeLaunchPolicy.orderedAvailableTargets(
            installedAppAvailable = installedApp != null,
            playStoreAvailable = playStore.resolveActivity(activity.packageManager) != null,
            webStoreAvailable = webStore.resolveActivity(activity.packageManager) != null
        )

        return candidates.any { target ->
            val intent = intents[target] ?: return@any false
            runCatching {
                activity.startActivity(intent)
                true
            }.getOrDefault(false)
        }
    }
}
