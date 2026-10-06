package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class ProxyActivityRecoveryContractTest {
    @Test
    fun geminiProxyReturnsToSetupWhenAssistantLaunchFails() {
        val source = findSource("src/main/java/nl/zennay/raiseai/AssistantProxyActivity.kt").readText()

        assertTrue(
            "Gemini proxy must inspect launch failure",
            source.contains("if (!launched.success) {")
        )
        assertSetupFallback(source)
    }

    @Test
    fun chatGptProxyReturnsToSetupWhenWearBrowserLaunchFails() {
        val source = findSource("src/main/java/nl/zennay/raiseai/ChatGptProxyActivity.kt").readText()

        assertTrue(
            "ChatGPT proxy must inspect launch failure",
            source.contains("if (!ChatGptLauncher.launchFromActivity(this)) {")
        )
        assertSetupFallback(source)
    }

    private fun assertSetupFallback(source: String) {
        assertTrue(
            "failed proxy launch must route to MainActivity",
            source.contains("Intent(this, MainActivity::class.java)")
        )
        assertTrue(
            "setup recovery must reuse an existing MainActivity",
            source.contains("Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP")
        )
        assertTrue(
            "proxy must finish after handing off",
            source.contains("finish()")
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
