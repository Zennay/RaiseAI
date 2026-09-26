package nl.zennay.raiseai

import android.app.NotificationManager
import android.content.Context

/**
 * Samsung Bedtime/Sleep mode normally enables a Do Not Disturb interruption filter.
 * Raise AI treats any active DND mode as a sleep/quiet-state signal when the user has
 * Sleep/DND pause enabled. We only read the current filter; Raise AI never changes DND.
 */
object SleepModePolicy {
    fun isSleepOrDndActive(context: Context): Boolean {
        val manager = context.getSystemService(NotificationManager::class.java)
        return when (manager.currentInterruptionFilter) {
            NotificationManager.INTERRUPTION_FILTER_PRIORITY,
            NotificationManager.INTERRUPTION_FILTER_ALARMS,
            NotificationManager.INTERRUPTION_FILTER_NONE -> true
            else -> false
        }
    }
}
