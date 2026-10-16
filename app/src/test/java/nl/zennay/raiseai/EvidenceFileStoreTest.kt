package nl.zennay.raiseai

import java.io.File
import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EvidenceFileStoreTest {
    @Test
    fun replacesExistingEvidenceAndCleansTemporaryFiles() {
        val directory = Files.createTempDirectory("raiseai-evidence").toFile()
        val destination = File(directory, "watch-e2e-evidence.json")
        destination.writeText("old\n")

        EvidenceFileStore.replace(destination, "new\n")

        assertEquals("new\n", destination.readText())
        assertFalse(File(directory, "watch-e2e-evidence.json.tmp").exists())
        assertFalse(File(directory, "watch-e2e-evidence.json.bak").exists())
    }

    @Test
    fun restoresPreviousEvidenceWhenReplacementRenameFails() {
        val directory = Files.createTempDirectory("raiseai-evidence").toFile()
        val destination = File(directory, "watch-e2e-evidence.json")
        destination.writeText("old\n")

        var replacementAttempted = false
        try {
            EvidenceFileStore.replace(destination, "new\n") { source, target ->
                if (source.name.endsWith(".tmp") && target == destination) {
                    replacementAttempted = true
                    false
                } else {
                    source.renameTo(target)
                }
            }
        } catch (_: java.io.IOException) {
            // Expected: replacement failure must not destroy the previous valid evidence.
        }

        assertTrue(replacementAttempted)
        assertTrue(destination.exists())
        assertEquals("old\n", destination.readText())
        assertFalse(File(directory, "watch-e2e-evidence.json.tmp").exists())
    }

    @Test
    fun restoresStaleBackupBeforeWritingNewEvidence() {
        val directory = Files.createTempDirectory("raiseai-evidence").toFile()
        val destination = File(directory, "watch-e2e-evidence.json")
        val backup = File(directory, "watch-e2e-evidence.json.bak")
        backup.writeText("recovered\n")

        EvidenceFileStore.replace(destination, "new\n")

        assertEquals("new\n", destination.readText())
        assertFalse(backup.exists())
    }
}
