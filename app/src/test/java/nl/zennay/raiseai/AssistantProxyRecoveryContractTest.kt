package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantProxyRecoveryContractTest {
    @Test
    fun failedGeminiNotificationLaunchOpensRaiseAiRepairScreen() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/AssistantProxyActivity.kt"
        ).readText()

        val result = source.indexOf("val result = AssistantLauncher.launchFromActivity(this)")
        val failure = source.indexOf("if (!result.success)", result)
        val mainActivity = source.indexOf("Intent(this, MainActivity::class.java)", failure)
        val finish = source.indexOf("finish()", mainActivity)

        assertTrue("proxy must inspect the Gemini launch result", result >= 0)
        assertTrue("failed Gemini launch must enter a recovery branch", failure > result)
        assertTrue("failure branch must open Raise AI for repair", mainActivity > failure)
        assertTrue("proxy should finish only after launching the repair screen", finish > mainActivity)
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
