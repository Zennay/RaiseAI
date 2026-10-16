package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BootRecoveryPolicyTest {
    @Test
    fun bootCompletedStartsOnlyWhenMonitoringIsEnabledAndCalibrated() {
        assertTrue(
            BootRecoveryPolicy.shouldStart(
                action = "android.intent.action.BOOT_COMPLETED",
                monitoringEnabled = true,
                calibrated = true
            )
        )
        assertFalse(
            BootRecoveryPolicy.shouldStart(
                action = "android.intent.action.BOOT_COMPLETED",
                monitoringEnabled = false,
                calibrated = true
            )
        )
        assertFalse(
            BootRecoveryPolicy.shouldStart(
                action = "android.intent.action.BOOT_COMPLETED",
                monitoringEnabled = true,
                calibrated = false
            )
        )
    }

    @Test
    fun packageReplacementCanRestoreAnEnabledCalibratedMonitor() {
        assertTrue(
            BootRecoveryPolicy.shouldStart(
                action = "android.intent.action.MY_PACKAGE_REPLACED",
                monitoringEnabled = true,
                calibrated = true
            )
        )
    }

    @Test
    fun unsupportedOrMissingBroadcastActionsFailClosedBeforeRecovery() {
        val actions = listOf(
            null,
            "android.intent.action.PACKAGE_REPLACED",
            "com.example.FORGED_BOOT"
        )

        actions.forEach { action ->
            assertFalse(BootRecoveryPolicy.isRecoveryAction(action))
            assertFalse(
                BootRecoveryPolicy.shouldStart(
                    action = action,
                    monitoringEnabled = true,
                    calibrated = true
                )
            )
        }
    }
}
