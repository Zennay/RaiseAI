package nl.zennay.raiseai

import android.app.NotificationManager
import android.content.Context

/**
 * Samsung Bedtime/Sleep mode normally enables a Do Not Disturb interruption filter.
 * Raise AI treats any active DND mode as a sleep/quiet-state signal when the user has
 * Sleep/DND pause enabled. We only read the current filter; Raise AI never changes DND.
 *
 * Unknown or unreadable interruption state fails closed to paused. False-positive
 * raise triggers during sleep/quiet time are worse than temporarily requiring the user
 * to disable Sleep/DND pause when Android cannot report a trustworthy state.
 */
object SleepModePolicy {
    internal fun shouldPause(interruptionFilter: Int?): Boolean =
        when (interruptionFilter) {
            NotificationManager.INTERRUPTION_FILTER_ALL -> false
            NotificationManager.INTERRUPTION_FILTER_PRIORITY,
            NotificationManager.INTERRUPTION_FILTER_ALARMS,
            NotificationManager.INTERRUPTION_FILTER_NONE -> true
            else -> true
        }

    fun isSleepOrDndActive(context: Context): Boolean {
        val interruptionFilter = runCatching {
            context.getSystemService(NotificationManager::class.java)
                ?.currentInterruptionFilter
        }.getOrNull()

        return shouldPause(interruptionFilter)
    }
}
