package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class SensorTraceRecorderRecoveryContractTest {
    @Test
    fun emptyTraceFileIsReinitializedBeforeAppend() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/SensorTraceRecorder.kt"
        ).readText()

        assertTrue(
            "an interrupted first write may leave an empty trace that still needs the canonical header",
            source.contains("if (!file.exists() || file.length() == 0L)")
        )
        assertTrue(
            "empty-file recovery must restore the canonical CSV header",
            source.contains("file.writeText(\"\$HEADER\\n\")")
        )
        assertTrue(
            "header recovery must happen before sample append",
            source.indexOf("file.writeText(\"$HEADER\\n\")") < source.indexOf("file.appendText(")
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
