package nl.zennay.raiseai

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.os.SystemClock
import android.util.Log

/**
 * Prevents accidental assistant reopen loops while still allowing a fresh wrist gesture to start
 * another dictation once Raise AI is ready again.
 *
 * With Usage Access we inspect the most recent foreground app. When Raise AI itself is foreground,
 * the WebExtension/native bridge decides whether a gesture is safe based on the live voice state.
 * Without Usage Access we keep a conservative fallback lock.
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

        if (foregroundPackage == context.packageName) {
            return NativeSessionState.isBusy() || WearBridge.shouldBlockGesture()
        }

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
            val transitions = mutableListOf<ForegroundTransition>()

            while (events.hasNextEvent()) {
                events.getNextEvent(event)
                val resumed =
                    event.eventType == UsageEvents.Event.ACTIVITY_RESUMED ||
                    event.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND
                val backgrounded =
                    event.eventType == UsageEvents.Event.ACTIVITY_PAUSED ||
                    event.eventType == UsageEvents.Event.MOVE_TO_BACKGROUND ||
                    event.eventType == UsageEvents.Event.ACTIVITY_STOPPED

                if (resumed || backgrounded) {
                    val activityScoped =
                        event.eventType == UsageEvents.Event.ACTIVITY_RESUMED ||
                        event.eventType == UsageEvents.Event.ACTIVITY_PAUSED ||
                        event.eventType == UsageEvents.Event.ACTIVITY_STOPPED
                    transitions += ForegroundTransition(
                        packageName = event.packageName.orEmpty(),
                        timestampMs = event.timeStamp,
                        resumed = resumed,
                        activityName = if (activityScoped) event.className.orEmpty() else "",
                        packageWide = !activityScoped
                    )
                }
            }

            ForegroundActivityState.currentPackage(transitions.asSequence())
        }.getOrElse {
            Log.w(TAG, "Could not read foreground app; using fallback session lock", it)
            null
        }
    }

    companion object {
        private const val TAG = "RaiseAI.SessionGuard"

        // The gesture detector itself already has a 3-second cooldown and explicit wrist-away
        // rearming. This shorter lock only absorbs duplicate Activity launches from one trigger.
        private const val MINIMUM_SESSION_LOCK_MS = 1_500L
        private const val FALLBACK_SESSION_LOCK_MS = 30_000L
        private const val FOREGROUND_LOOKBACK_MS = 60L * 60L * 1_000L
    }
}