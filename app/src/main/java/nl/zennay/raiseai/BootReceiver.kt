package nl.zennay.raiseai

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import android.util.Log

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED && action != Intent.ACTION_MY_PACKAGE_REPLACED) return

        // Never restore a foreground monitor that cannot launch the selected
        // assistant. Both Gemini and native voice require the background-activity
        // launch grant for a raise detected while the Watch app is not visible.
        val enabled = runCatching { CalibrationStore.isMonitoringEnabled(context) }
            .getOrElse {
                Log.w(TAG, "Could not read saved monitoring state after $action", it)
                return
            }
        if (!enabled) return

        val calibrated = runCatching { CalibrationStore.loadPose(context) != null }
            .getOrElse {
                Log.w(TAG, "Could not load calibration after $action", it)
                false
            }
        val backgroundGranted = calibrated &&
            runCatching { Settings.canDrawOverlays(context) }.getOrElse {
                Log.w(TAG, "Could not check background assistant grant after $action", it)
                false
            }

        when (BootMonitoringRestorePolicy.decide(enabled, calibrated, backgroundGranted)) {
            BootMonitoringRestorePolicy.Decision.SKIP -> return
            BootMonitoringRestorePolicy.Decision.DISABLE_UNUSABLE_MONITORING -> {
                // Do not show "monitoring on" when gestures cannot open anything.
                runCatching { CalibrationStore.setMonitoringEnabled(context, false) }
                    .onFailure { Log.w(TAG, "Could not clear unusable monitoring state", it) }
                Log.w(TAG, "Monitoring restore skipped: calibration or background grant missing")
                return
            }
            BootMonitoringRestorePolicy.Decision.START -> Unit
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
            // The boot restoration did not succeed. Avoid advertising monitoring
            // as active until the user deliberately retries from the Watch UI.
            runCatching { CalibrationStore.setMonitoringEnabled(context, false) }
                .onFailure { persistError ->
                    Log.w(TAG, "Could not clear monitoring after failed service start", persistError)
                }
        }
    }

    companion object {
        private const val TAG = "RaiseAI.Boot"
    }
}
