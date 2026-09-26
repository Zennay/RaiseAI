package nl.zennay.raiseai

import android.app.Activity
import android.content.Intent
import android.net.Uri

object HomeLauncher {
    private const val HOME_PACKAGE = "com.google.android.apps.chromecast.app"

    fun open(activity: Activity): Boolean {
        val launch = activity.packageManager.getLaunchIntentForPackage(HOME_PACKAGE)
        if (launch != null) {
            return runCatching {
                activity.startActivity(launch)
                true
            }.getOrDefault(false)
        }

        val marketIntent = Intent(
            Intent.ACTION_VIEW,
            Uri.parse("market://details?id=$HOME_PACKAGE")
        )
        return runCatching {
            activity.startActivity(marketIntent)
            true
        }.getOrDefault(false)
    }
}
