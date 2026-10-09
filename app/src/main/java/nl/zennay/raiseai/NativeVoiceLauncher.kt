package nl.zennay.raiseai

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.util.Log

object NativeVoiceLauncher {
    private const val TAG = "RaiseAI.NativeVoice"

    fun launchFromActivity(activity: Activity): Boolean = runCatching {
        activity.startActivity(intent(activity))
        CalibrationStore.recordAssistantLaunch(activity, "NATIVE_VOICE")
        true
    }.getOrElse {
        Log.e(TAG, "Could not open native voice UI", it)
        CalibrationStore.recordAssistantLaunch(activity, "NATIVE_VOICE_FAILED")
        false
    }

    fun launchFromService(context: Context): Boolean {
        if (!BackgroundLaunchGrant.isGranted(context)) {
            CalibrationStore.recordAssistantLaunch(
                context,
                "NATIVE_VOICE_BLOCKED_NO_BACKGROUND_GRANT"
            )
            return false
        }

        return runCatching {
            context.startActivity(intent(context).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            })
            CalibrationStore.recordAssistantLaunch(context, "NATIVE_VOICE_BACKGROUND")
            true
        }.getOrElse {
            Log.e(TAG, "Background native voice launch failed", it)
            CalibrationStore.recordAssistantLaunch(
                context,
                "NATIVE_VOICE_BACKGROUND_FAILED"
            )
            false
        }
    }

    private fun intent(context: Context): Intent =
        Intent(context, NativeVoiceActivity::class.java)
}
