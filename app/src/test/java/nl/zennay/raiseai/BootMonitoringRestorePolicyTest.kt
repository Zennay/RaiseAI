package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Test

class BootMonitoringRestorePolicyTest {
    private fun decision(
        enabled: Boolean,
        calibrated: Boolean,
        backgroundGranted: Boolean
    ) = BootMonitoringRestorePolicy.decide(enabled, calibrated, backgroundGranted)

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
                    assertEquals(
                        enabled && calibrated && grant,
                        decision(enabled, calibrated, grant) ==
                            BootMonitoringRestorePolicy.Decision.START
                    )
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
}
