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

        val target = HomeLaunchPolicy.choose(
            installedAppAvailable = installedApp != null,
            playStoreAvailable = playStore.resolveActivity(activity.packageManager) != null,
            webStoreAvailable = webStore.resolveActivity(activity.packageManager) != null
        )

        val intent = when (target) {
            HomeLaunchTarget.INSTALLED_APP -> installedApp
            HomeLaunchTarget.PLAY_STORE -> playStore
            HomeLaunchTarget.WEB_STORE -> webStore
            HomeLaunchTarget.UNAVAILABLE -> null
        } ?: return false

        return runCatching {
            activity.startActivity(intent)
            true
        }.getOrDefault(false)
    }
}
