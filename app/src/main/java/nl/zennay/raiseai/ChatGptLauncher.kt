package nl.zennay.raiseai

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.util.Log

/** Opens the user's real ChatGPT web session in the bundled Wear browser. */
object ChatGptLauncher {
    private const val TAG = "RaiseAI.ChatGPT"
    const val SAMSUNG_BROWSER_PACKAGE = "com.sec.android.app.sbrowser"

    fun routeLabel(): String = "RaiseGPT Wear UI"

    fun launchFromActivity(activity: Activity, tryWebsiteMic: Boolean = true): Boolean = runCatching {
        activity.startActivity(intent(activity, tryWebsiteMic))
        CalibrationStore.recordAssistantLaunch(activity, routePath(activity, background = false))
        true
    }.getOrElse {
        Log.e(TAG, "Could not open ChatGPT Web", it)
        CalibrationStore.recordAssistantLaunch(activity, "CHATGPT_WEB_FAILED")
        false
    }

    fun launchFromService(context: Context): Boolean {
        if (!Settings.canDrawOverlays(context)) {
            CalibrationStore.recordAssistantLaunch(context, "CHATGPT_BLOCKED_NO_BACKGROUND_GRANT")
            Log.w(TAG, "Background launch grant missing; run installer again")
            return false
        }

        return runCatching {
            context.startActivity(intent(context).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            })
            CalibrationStore.recordAssistantLaunch(context, routePath(context, background = true))
            true
        }.getOrElse {
            Log.e(TAG, "Background ChatGPT Web launch failed", it)
            CalibrationStore.recordAssistantLaunch(context, "CHATGPT_WEB_BACKGROUND_FAILED")
            false
        }
    }

    private fun intent(context: Context, tryWebsiteMic: Boolean = true): Intent = Intent(context, ChatGptActivity::class.java).apply {
        putExtra(ChatGptActivity.EXTRA_TRY_WEBSITE_MIC, tryWebsiteMic)
    }

    fun browserFallbackIntent(context: Context): Intent {
        val samsungInternet = Intent(Intent.ACTION_VIEW, Uri.parse(CHATGPT_URL)).apply {
            setPackage(SAMSUNG_BROWSER_PACKAGE)
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        if (samsungInternet.resolveActivity(context.packageManager) != null) {
            return samsungInternet
        }

        return Intent(Intent.ACTION_VIEW, Uri.parse(CHATGPT_URL)).apply {
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
    }

    private fun routePath(@Suppress("UNUSED_PARAMETER") context: Context, background: Boolean): String {
        val suffix = if (background) "_BACKGROUND" else ""
        return "CHATGPT_GECKOVIEW$suffix"
    }

    private const val CHATGPT_URL = "https://chatgpt.com/"
}
