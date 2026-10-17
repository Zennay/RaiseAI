package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class RaiseMonitoringSetupTest {
    @Test
    fun cannotStartWithoutCalibratedPose() {
        assertEquals(
            RaiseMonitoringSetup.Result.NEEDS_CALIBRATION,
            RaiseMonitoringSetup.check(calibrated = false, backgroundLaunchAllowed = true)
        )
    }

    @Test
    fun missingBackgroundGrantBlocksMonitoringBeforeServiceStarts() {
        assertEquals(
            RaiseMonitoringSetup.Result.NEEDS_BACKGROUND_GRANT,
            RaiseMonitoringSetup.check(calibrated = true, backgroundLaunchAllowed = false)
        )
    }

    @Test
    fun calibrationFailureIsShownFirstWhenBothPrerequisitesAreMissing() {
        assertEquals(
            RaiseMonitoringSetup.Result.NEEDS_CALIBRATION,
            RaiseMonitoringSetup.check(calibrated = false, backgroundLaunchAllowed = false)
        )
    }

    @Test
    fun calibratedWatchWithGrantCanStartMonitoring() {
        assertEquals(
            RaiseMonitoringSetup.Result.READY,
            RaiseMonitoringSetup.check(calibrated = true, backgroundLaunchAllowed = true)
        )
    }
}
