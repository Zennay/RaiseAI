package nl.zennay.raiseai

import android.app.NotificationManager
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SleepModePolicyTest {
    @Test
    fun allFilterKeepsMonitoringActive() {
        assertFalse(
            SleepModePolicy.shouldPause(
                NotificationManager.INTERRUPTION_FILTER_ALL
            )
        )
    }

    @Test
    fun everyQuietFilterPausesMonitoring() {
        listOf(
            NotificationManager.INTERRUPTION_FILTER_PRIORITY,
            NotificationManager.INTERRUPTION_FILTER_ALARMS,
            NotificationManager.INTERRUPTION_FILTER_NONE
        ).forEach { filter ->
            assertTrue("expected filter $filter to pause monitoring", SleepModePolicy.shouldPause(filter))
        }
    }

    @Test
    fun unknownFilterFailsClosedToPaused() {
        assertTrue(
            SleepModePolicy.shouldPause(
                NotificationManager.INTERRUPTION_FILTER_UNKNOWN
            )
        )
    }

    @Test
    fun missingFilterFailsClosedToPaused() {
        assertTrue(SleepModePolicy.shouldPause(null))
    }

    @Test
    fun futureUnsupportedFilterFailsClosedToPaused() {
        assertTrue(SleepModePolicy.shouldPause(Int.MAX_VALUE))
    }
}
