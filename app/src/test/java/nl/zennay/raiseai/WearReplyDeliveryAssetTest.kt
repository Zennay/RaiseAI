package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class WearReplyDeliveryAssetTest {
    @Test
    fun eachAssistantWaitAllowsTheSameTextToBeDeliveredAgain() {
        val script = findAsset("src/main/assets/raiseai_wear/wear.js").readText()
        val start = script.indexOf("function beginAssistantWait()")
        val end = script.indexOf("function deliverAssistantReply", start)

        assertTrue("beginAssistantWait must exist", start >= 0)
        assertTrue("deliverAssistantReply must follow beginAssistantWait", end > start)

        val beginAssistantWait = script.substring(start, end)
        assertTrue(
            "a new request must clear cross-request reply deduplication",
            beginAssistantWait.contains("lastDeliveredAssistant = \"\";")
        )
    }

    private fun findAsset(relativePath: String): File {
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
