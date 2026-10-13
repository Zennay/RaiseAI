package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class BootMonitoringRestorePolicyTest {
    private fun decision(
        enabled: Boolean,
        calibrated: Boolean,
        backgroundGranted: Boolean,
        accelerometerAvailable: Boolean = true
    ) = BootMonitoringRestorePolicy.decide(enabled, calibrated, backgroundGranted, accelerometerAvailable)

    @Test
    fun fullyConfiguredEnabledMonitorCanRestart() {
        assertEquals(
            BootMonitoringRestorePolicy.Decision.START,
            decision(enabled = true, calibrated = true, backgroundGranted = true)
        )
    }

    @Test
    fun userDisabledMonitorStaysDisabled() {
        for (calibrated in listOf(false, true)) {
            for (grant in listOf(false, true)) {
                assertEquals(
                    BootMonitoringRestorePolicy.Decision.SKIP,
                    decision(enabled = false, calibrated = calibrated, backgroundGranted = grant)
                )
            }
        }
    }

    @Test
    fun previouslyEnabledMonitorWithoutCalibrationIsDisabled() {
        for (grant in listOf(false, true)) {
            assertEquals(
                BootMonitoringRestorePolicy.Decision.DISABLE_UNUSABLE_MONITORING,
                decision(enabled = true, calibrated = false, backgroundGranted = grant)
            )
        }
    }

    @Test
    fun previouslyEnabledMonitorWithoutBackgroundGrantIsDisabled() {
        assertEquals(
            BootMonitoringRestorePolicy.Decision.DISABLE_UNUSABLE_MONITORING,
            decision(enabled = true, calibrated = true, backgroundGranted = false)
        )
    }

    @Test
    fun exhaustiveInputsNeverRestartUnlessAllPrerequisitesHold() {
        for (enabled in listOf(false, true)) {
            for (calibrated in listOf(false, true)) {
                for (grant in listOf(false, true)) {
                    for (accelerometer in listOf(false, true)) {
                        assertEquals(
                            enabled && calibrated && grant && accelerometer,
                            decision(enabled, calibrated, grant, accelerometer) ==
                                BootMonitoringRestorePolicy.Decision.START
                        )
                    }
                }
            }
        }
    }

    @Test
    fun missingPrerequisitesAreNotMistakenForUserOptOut() {
        assertEquals(
            BootMonitoringRestorePolicy.Decision.SKIP,
            decision(enabled = false, calibrated = true, backgroundGranted = true)
        )
        assertEquals(
            BootMonitoringRestorePolicy.Decision.DISABLE_UNUSABLE_MONITORING,
            decision(enabled = true, calibrated = false, backgroundGranted = true)
        )
        assertEquals(
            BootMonitoringRestorePolicy.Decision.DISABLE_UNUSABLE_MONITORING,
            decision(enabled = true, calibrated = true, backgroundGranted = false)
        )
    }

    @Test
    fun validUnitAndSlightlyRoundedCalibrationRemainUsable() {
        assertEquals(true, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(0f, 0f, 1f)))
        assertEquals(true, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(0.6f, 0.8f, 0f)))
        assertEquals(true, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(0.61f, 0.79f, 0.02f)))
    }

    @Test
    fun absentAndZeroCalibrationCannotRestoreMonitoring() {
        assertEquals(false, BootMonitoringRestorePolicy.hasUsableCalibration(null))
        assertEquals(false, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(0f, 0f, 0f)))
    }

    @Test
    fun nonFiniteCalibrationNeverQualifiesForBootRestore() {
        for (bad in listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY)) {
            assertEquals(false, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(bad, 0f, 1f)))
            assertEquals(false, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(0f, bad, 1f)))
            assertEquals(false, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(0f, 1f, bad)))
        }
    }

    @Test
    fun implausiblyLargeOrSmallCalibrationIsRejected() {
        assertEquals(false, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(0f, 0f, 0.1f)))
        assertEquals(false, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(0f, 0f, 10f)))
        assertEquals(false, BootMonitoringRestorePolicy.hasUsableCalibration(MouthPose(Float.MAX_VALUE, 0f, 0f)))
    }

    @Test
    fun sensorUnavailableDisablesPreviouslyEnabledMonitor() {
        assertEquals(
            BootMonitoringRestorePolicy.Decision.DISABLE_UNUSABLE_MONITORING,
            decision(
                enabled = true, calibrated = true,
                backgroundGranted = true, accelerometerAvailable = false
            )
        )
    }

    @Test
    fun sensorFailureMustNotChangeUserOptOut() {
        assertEquals(
            BootMonitoringRestorePolicy.Decision.SKIP,
            decision(
                enabled = false, calibrated = true,
                backgroundGranted = true, accelerometerAvailable = false
            )
        )
    }
}
