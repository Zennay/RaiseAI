package nl.zennay.raiseai

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val monitoringEnabled = CalibrationStore.isMonitoringEnabled(context)
        val hasCalibration = if (monitoringEnabled) {
            CalibrationStore.loadPose(context) != null
        } else {
            false
        }

        if (!BootStartPolicy.shouldStart(intent.action, monitoringEnabled, hasCalibration)) return

        val service = Intent(context, GestureMonitorService::class.java)
        runCatching {
            if (Build.VERSION.SDK_INT >= 26) {
                context.startForegroundService(service)
            } else {
                context.startService(service)
            }
        }.onFailure {
            Log.w(TAG, "Could not auto-start Raise AI after " + intent.action, it)
        }
    }

    companion object {
        private const val TAG = "RaiseAI.Boot"
    }
}
