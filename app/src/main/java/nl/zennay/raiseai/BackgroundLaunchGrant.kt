package nl.zennay.raiseai

import android.content.Context
import android.provider.Settings

internal object BackgroundLaunchGrant {
    fun isGranted(context: Context): Boolean =
        isGranted { Settings.canDrawOverlays(context) }

    internal fun isGranted(check: () -> Boolean): Boolean =
        runCatching(check).getOrDefault(false)
}
