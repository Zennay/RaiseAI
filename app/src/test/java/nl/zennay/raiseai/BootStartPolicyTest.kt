package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BootStartPolicyTest {
    @Test
    fun allowsBootWhenMonitoringIsEnabledAndCalibrated() {
        assertTrue(
            BootStartPolicy.shouldStart(
                action = "android.intent.action.BOOT_COMPLETED",
                monitoringEnabled = true,
                hasCalibration = true
            )
        )
    }

    @Test
    fun allowsPackageReplacementWhenMonitoringIsEnabledAndCalibrated() {
        assertTrue(
            BootStartPolicy.shouldStart(
                action = "android.intent.action.MY_PACKAGE_REPLACED",
                monitoringEnabled = true,
                hasCalibration = true
            )
        )
    }

    @Test
    fun rejectsUnexpectedOrMissingActions() {
        assertFalse(BootStartPolicy.shouldStart(null, true, true))
        assertFalse(BootStartPolicy.shouldStart("nl.zennay.raiseai.FAKE_BOOT", true, true))
    }

    @Test
    fun requiresBothMonitoringOptInAndCalibration() {
        assertFalse(BootStartPolicy.shouldStart("android.intent.action.BOOT_COMPLETED", false, true))
        assertFalse(BootStartPolicy.shouldStart("android.intent.action.BOOT_COMPLETED", true, false))
        assertFalse(BootStartPolicy.shouldStart("android.intent.action.BOOT_COMPLETED", false, false))
    }
}
