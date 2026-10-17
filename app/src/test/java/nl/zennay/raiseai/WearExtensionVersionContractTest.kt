package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WearExtensionVersionContractTest {
    @Test
    fun bundledExtensionVersionTracksAppVersion() {
        val manifest = findProjectFile(
            "app/src/main/assets/raiseai_wear/manifest.json"
        ).readText()
        val appVersion = findProjectFile("VERSION.txt").readText().trim()

        assertTrue("VERSION.txt must not be blank", appVersion.isNotBlank())

        val extensionVersion = Regex(
            """(?m)^\s*"version"\s*:\s*"([^"]+)"\s*,?\s*$"""
        ).find(manifest)?.groupValues?.get(1)

        assertEquals(
            "Bundled GeckoView extension version must match the app release version. " +
                "ensureBuiltIn() skips reinstalling an already-installed built-in extension " +
                "when its version is unchanged, which can leave stale Wear bridge assets active.",
            appVersion,
            extensionVersion
        )
    }

    private fun findProjectFile(relativePath: String): File {
        var current = File(System.getProperty("user.dir")).canonicalFile
        repeat(8) {
            val candidate = File(current, relativePath)
            if (candidate.isFile) return candidate.canonicalFile
            current = current.parentFile ?: return@repeat
        }
        error("Could not locate " + relativePath + " from " + System.getProperty("user.dir"))
    }
}
