package nl.zennay.raiseai

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        if (!BootRecoveryPolicy.isRecoveryAction(action)) return

        val monitoringResult = runCatching {
            CalibrationStore.isMonitoringEnabled(context)
        }
        if (monitoringResult.isFailure) {
            Log.w(
                TAG,
                "Could not read monitoring state after $action",
                monitoringResult.exceptionOrNull()
            )
            return
        }

        val monitoringEnabled = monitoringResult.getOrDefault(false)
        if (!monitoringEnabled) return

        val calibrationResult = runCatching {
            CalibrationStore.loadPose(context) != null
        }
        if (calibrationResult.isFailure) {
            Log.w(
                TAG,
                "Could not read calibration state after $action",
                calibrationResult.exceptionOrNull()
            )
            return
        }

        if (!BootRecoveryPolicy.shouldStart(
                action = action,
                monitoringEnabled = monitoringEnabled,
                calibrated = calibrationResult.getOrDefault(false)
            )
        ) {
            return
        }

        val service = Intent(context, GestureMonitorService::class.java)
        runCatching {
            if (Build.VERSION.SDK_INT >= 26) {
                context.startForegroundService(service)
            } else {
                context.startService(service)
            }
        }.onFailure {
            Log.w(TAG, "Could not auto-start Raise AI after $action", it)
        }
    }

    companion object {
        private const val TAG = "RaiseAI.Boot"
    }
}
