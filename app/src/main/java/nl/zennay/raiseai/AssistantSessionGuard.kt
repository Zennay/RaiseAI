package nl.zennay.raiseai

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.os.SystemClock
import android.util.Log

/**
 * Prevents Raise AI from reopening ChatGPT or Gemini while an assistant session is active.
 *
 * With Usage Access (granted by the dev installer), we inspect the most recent foreground app.
 * Without Usage Access we fall back to a conservative time lock so the watch never enters a
 * rapid open/reopen loop.
 */
class AssistantSessionGuard(private val context: Context) {
    private var lastLaunchElapsedMs = Long.MIN_VALUE / 2

    fun markAssistantLaunched(nowElapsedMs: Long = SystemClock.elapsedRealtime()) {
        lastLaunchElapsedMs = nowElapsedMs
    }

    fun shouldBlockLaunch(nowElapsedMs: Long = SystemClock.elapsedRealtime()): Boolean {
        val ageMs = nowElapsedMs - lastLaunchElapsedMs
        if (ageMs < MINIMUM_SESSION_LOCK_MS) return true

        val foregroundPackage = currentForegroundPackage()
        if (foregroundPackage == AssistantLauncher.GOOGLE_WEAR_ASSISTANT_PACKAGE) return true
        if (foregroundPackage == ChatGptLauncher.SAMSUNG_BROWSER_PACKAGE) return true
        if (foregroundPackage == context.packageName) return true
        if (foregroundPackage != null) return false

        // If Usage Access is unavailable or Android returns no recent foreground event,
        // use a safe fallback instead of allowing repeated assistant launches.
        return ageMs < FALLBACK_SESSION_LOCK_MS
    }

    fun hasUsageAccess(): Boolean {
        val appOps = context.getSystemService(AppOpsManager::class.java)
        val mode = appOps.unsafeCheckOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            context.applicationInfo.uid,
            context.packageName
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun currentForegroundPackage(): String? {
        if (!hasUsageAccess()) return null

        return runCatching {
            val usage = context.getSystemService(UsageStatsManager::class.java)
            val now = System.currentTimeMillis()
            val events = usage.queryEvents(now - FOREGROUND_LOOKBACK_MS, now)
            val event = UsageEvents.Event()
            var latestPackage: String? = null
            var latestTimestamp = Long.MIN_VALUE

            while (events.hasNextEvent()) {
                events.getNextEvent(event)
                val resumed = event.eventType == UsageEvents.Event.ACTIVITY_RESUMED ||
                    event.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND
                if (resumed && event.timeStamp >= latestTimestamp) {
                    latestTimestamp = event.timeStamp
                    latestPackage = event.packageName
                }
            }
            latestPackage
        }.getOrElse {
            Log.w(TAG, "Could not read foreground app; using fallback session lock", it)
            null
        }
    }

    companion object {
        private const val TAG = "RaiseAI.SessionGuard"
        private const val MINIMUM_SESSION_LOCK_MS = 5_000L
        private const val FALLBACK_SESSION_LOCK_MS = 45_000L
        private const val FOREGROUND_LOOKBACK_MS = 60L * 60L * 1_000L
    }
}
