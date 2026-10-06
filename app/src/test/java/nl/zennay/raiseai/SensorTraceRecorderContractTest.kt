package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class SensorTraceRecorderContractTest {
    @Test
    fun emptyTraceFileIsReinitializedWithCsvHeaderBeforeAppend() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/SensorTraceRecorder.kt"
        ).readText()

        assertTrue(
            "trace recorder must define one canonical CSV header",
            source.contains("private const val CSV_HEADER = \"label,session_id,elapsed_ms,x,y,z\\n\"")
        )
        assertTrue(
            "an interrupted first write may leave an empty file that still needs a header",
            source.contains("if (!file.exists() || file.length() == 0L)")
        )
        assertTrue(
            "header recovery must happen before sample append",
            source.indexOf("file.writeText(CSV_HEADER)") < source.indexOf("file.appendText(")
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
