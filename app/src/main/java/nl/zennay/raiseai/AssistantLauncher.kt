package nl.zennay.raiseai

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.util.Log

object AssistantLauncher {
    private const val TAG = "RaiseAI.Assistant"
    const val GOOGLE_WEAR_ASSISTANT_PACKAGE = "com.google.android.wearable.assistant"

    data class LaunchResult(
        val success: Boolean,
        val path: String
    )

    private fun googleAssistIntent(): Intent = Intent(Intent.ACTION_ASSIST).apply {
        setPackage(GOOGLE_WEAR_ASSISTANT_PACKAGE)
    }

    /**
     * Verified on the user's Galaxy Watch 7: an explicit ACTION_ASSIST scoped to
     * Google's Wear assistant package opens Gemini/Google and enters listening.
     * Do not add ACTION_VOICE_COMMAND here: Samsung routes that to Bixby.
     */
    fun launchFromActivity(activity: Activity): LaunchResult {
        val started = runCatching {
            activity.startActivity(googleAssistIntent())
            true
        }.getOrElse {
            Log.e(TAG, "Explicit Google ACTION_ASSIST failed", it)
            false
        }

        val path = if (started) "GOOGLE_ASSIST" else "GOOGLE_ASSIST_FAILED"
        CalibrationStore.recordAssistantLaunch(activity, path)
        return LaunchResult(started, path)
    }

    /**
     * GestureMonitorService runs while Raise AI itself is not visible. Android
     * normally blocks surprise activity launches from that state. For this
     * personal sideload build the installer grants SYSTEM_ALERT_WINDOW through
     * ADB (Wear OS 4+ removed the normal settings UI for granting it). Android's
     * BAL rules list this permission as a background-activity-start exception.
     *
     * We never draw an overlay; the permission is used only to let the user's
     * deliberate raise-to-mouth gesture invoke the already-verified Gemini
     * ACTION_ASSIST route.
     */
    fun launchFromService(context: Context): LaunchResult {
        if (!BackgroundLaunchGrant.isGranted(context)) {
            val path = "BLOCKED_NO_BACKGROUND_LAUNCH_GRANT"
            CalibrationStore.recordAssistantLaunch(context, path)
            Log.w(TAG, "Background launch grant missing; run installer again")
            return LaunchResult(false, path)
        }

        val intent = googleAssistIntent().apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }

        val started = runCatching {
            context.startActivity(intent)
            true
        }.getOrElse {
            Log.e(TAG, "Background Google ACTION_ASSIST failed", it)
            false
        }

        val path = if (started) "GOOGLE_ASSIST_BACKGROUND" else "GOOGLE_ASSIST_BACKGROUND_FAILED"
        CalibrationStore.recordAssistantLaunch(context, path)
        return LaunchResult(started, path)
    }
}
