package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeVoiceLifecycleContractTest {
    @Test
    fun asynchronousGatewayOutcomeIsRecordedOnlyInsideActiveUiDelivery() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/NativeVoiceActivity.kt"
        ).readText()

        assertOutcomeWriteIsLifecycleGated(
            source = source,
            blockStart = ".onSuccess { response ->",
            blockEnd = ".onFailure { error ->",
            evidenceWrite = "WatchE2eEvidence.recordSuccess("
        )
        assertOutcomeWriteIsLifecycleGated(
            source = source,
            blockStart = ".onFailure { error ->",
            blockEnd = "private fun postToUiIfActive",
            evidenceWrite = "WatchE2eEvidence.recordFailure("
        )
    }

    private fun assertOutcomeWriteIsLifecycleGated(
        source: String,
        blockStart: String,
        blockEnd: String,
        evidenceWrite: String
    ) {
        val start = source.indexOf(blockStart)
        val end = source.indexOf(blockEnd, start + blockStart.length)
        assertTrue("expected gateway outcome block: $blockStart", start >= 0)
        assertTrue("expected gateway outcome block end: $blockEnd", end > start)

        val block = source.substring(start, end)
        val gate = block.indexOf("postToUiIfActive {")
        val evidence = block.indexOf(evidenceWrite)

        assertTrue("gateway outcome must enter the active-UI gate", gate >= 0)
        assertTrue("expected evidence write: $evidenceWrite", evidence >= 0)
        assertTrue(
            "evidence must not be committed before the active-UI lifecycle gate",
            evidence > gate
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
