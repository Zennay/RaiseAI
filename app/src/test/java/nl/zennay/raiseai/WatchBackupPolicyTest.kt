package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WatchBackupPolicyTest {
    @Test
    fun watchSpecificCalibrationAndMonitoringStateCannotBeRestoredFromAndroidBackup() {
        val manifest = findManifest().readText()

        assertTrue(
            "Watch app must disable Android backup so device-specific calibration and monitoring state cannot be restored",
            manifest.contains("android:allowBackup=\"false\"")
        )
        assertFalse(
            "Watch app must not silently re-enable Android backup",
            manifest.contains("android:allowBackup=\"true\"")
        )
    }

    private fun findManifest(): File {
        var current = File(System.getProperty("user.dir")).canonicalFile
        repeat(6) {
            listOf(
                File(current, "src/main/AndroidManifest.xml"),
                File(current, "app/src/main/AndroidManifest.xml")
            ).firstOrNull(File::isFile)?.let { return it.canonicalFile }
            current = current.parentFile ?: return@repeat
        }
        error(
            "Could not locate app/src/main/AndroidManifest.xml from " +
                System.getProperty("user.dir")
        )
    }
}
