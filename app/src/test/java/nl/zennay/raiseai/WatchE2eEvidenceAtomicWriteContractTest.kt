package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WatchE2eEvidenceAtomicWriteContractTest {
    @Test
    fun evidenceReplacementUsesAtomicFileCommitAndRollback() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/WatchE2eEvidence.kt"
        ).readText()

        assertTrue(
            "evidence writer must use AtomicFile for crash-safe replacement",
            source.contains("AtomicFile(File(context.filesDir, FILE_NAME))")
        )
        assertTrue(
            "atomic write must start through AtomicFile",
            source.contains("val output = atomicFile.startWrite()")
        )
        assertTrue(
            "successful evidence writes must be committed atomically",
            source.contains("atomicFile.finishWrite(output)")
        )
        assertTrue(
            "failed evidence writes must restore the previous file",
            source.contains("atomicFile.failWrite(output)")
        )
        assertTrue(
            "write failures must remain observable to the caller",
            source.contains("throw error")
        )
        assertFalse(
            "writer must not delete last known-good evidence before replacement",
            source.contains("destination.delete()")
        )
        assertFalse(
            "writer must not rely on manual rename fallback",
            source.contains("renameTo(destination)")
        )
    }

    private fun findSource(relativePath: String): File {
        var current = File(System.getProperty("user.dir")).canonicalFile
        repeat(6) {
            listOf(
                File(current, relativePath),
                File(current, "app/" + relativePath)
            ).firstOrNull(File::isFile)?.let { return it.canonicalFile }
            current = current.parentFile ?: return@repeat
        }
        error("Could not locate " + relativePath + " from " + System.getProperty("user.dir"))
    }
}
