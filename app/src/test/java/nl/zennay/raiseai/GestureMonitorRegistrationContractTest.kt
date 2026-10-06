package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class GestureMonitorRegistrationContractTest {
    @Test
    fun failedSensorRegistrationCannotRemainReady() {
        val source = sourceFile().readText()

        assertTrue(
            source.contains(
                "else if (registerAccelerometer()) {\n" +
                    "            updateNotification(\"Raise your watch to your mouth for Raise AI\")\n" +
                    "        } else {"
            )
        )
        assertTrue(source.contains("CalibrationStore.setMonitoringEnabled(this, false)"))
        assertTrue(source.contains("Accelerometer registration failed; stopping monitor"))
        assertTrue(source.contains("stopSelf()"))
        assertTrue(source.contains("if (!applyPowerState(force = true)) return"))
        assertTrue(
            source.contains(
                "return if (applyPowerState()) START_STICKY else START_NOT_STICKY"
            )
        )
        assertTrue(source.contains("private fun applyPowerState(force: Boolean = false): Boolean"))
        assertTrue(source.contains("private fun registerAccelerometer(): Boolean"))
        assertTrue(source.contains("sensorRegistered = sensorManager.registerListener("))
        assertTrue(source.contains("return sensorRegistered"))
    }

    private fun sourceFile(): File {
        val candidates = listOf(
            File("src/main/java/nl/zennay/raiseai/GestureMonitorService.kt"),
            File("app/src/main/java/nl/zennay/raiseai/GestureMonitorService.kt")
        )
        return candidates.firstOrNull { it.isFile }
            ?: error("GestureMonitorService.kt not found from ${File(".").absolutePath}")
    }
}
