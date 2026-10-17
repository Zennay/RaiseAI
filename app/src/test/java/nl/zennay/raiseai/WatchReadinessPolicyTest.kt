package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WatchReadinessPolicyTest {
    @Test
    fun readyWhenAllCriticalPrerequisitesAreConfigured() {
        val summary = WatchReadinessPolicy.summarize(
            WatchReadinessInputs(
                calibrated = true,
                monitoringEnabled = true,
                handsFreeGrant = true,
                sessionGuardAccess = false,
                gatewayConfigured = true,
                sleepDndPauseEnabled = false
            )
        )

        assertEquals("✓ Raise AI ready", summary.headline)
        assertTrue(summary.lines.contains("○ Session guard fallback: 30 sec"))
        assertTrue(summary.lines.contains("○ Sleep/DND pause is off"))
    }

    @Test
    fun missingCriticalPrerequisitesProduceActionableSetupState() {
        val summary = WatchReadinessPolicy.summarize(
            WatchReadinessInputs(
                calibrated = false,
                monitoringEnabled = false,
                handsFreeGrant = false,
                sessionGuardAccess = true,
                gatewayConfigured = false,
                sleepDndPauseEnabled = true
            )
        )

        assertEquals("⚠ Setup needed", summary.headline)
        assertTrue(summary.lines.contains("○ Calibrate mouth pose"))
        assertTrue(summary.lines.contains("○ Enable raise-to-talk"))
        assertTrue(summary.lines.contains("○ Grant hands-free launch"))
        assertTrue(summary.lines.contains("○ Configure VPS gateway"))
    }

    @Test
    fun displayTextKeepsHeadlineAndEveryStatusVisible() {
        val summary = WatchReadinessPolicy.summarize(
            WatchReadinessInputs(
                calibrated = true,
                monitoringEnabled = true,
                handsFreeGrant = true,
                sessionGuardAccess = true,
                gatewayConfigured = true,
                sleepDndPauseEnabled = true
            )
        )

        val lines = summary.asDisplayText().lines()
        assertEquals("✓ Raise AI ready", lines.first())
        assertEquals(7, lines.size)
    }
}
