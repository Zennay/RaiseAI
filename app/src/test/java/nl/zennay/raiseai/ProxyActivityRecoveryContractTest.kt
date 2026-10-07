package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class ProxyActivityRecoveryContractTest {
    @Test
    fun chatGptProxyReturnsToSetupWhenWearBrowserLaunchFails() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/ChatGptProxyActivity.kt"
        ).readText()

        val failure = source.indexOf("if (!ChatGptLauncher.launchFromActivity(this))")
        val launch = source.indexOf("ChatGptLauncher.launchFromActivity(this)", failure)
        val recoveryCall = source.indexOf("openSetup()", launch)
        val finish = source.indexOf("finish()", recoveryCall)
        val setupIntent = source.indexOf("Intent(this, MainActivity::class.java)")
        val setupFlags = source.indexOf(
            "Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP",
            setupIntent
        )

        assertTrue("failed ChatGPT launch must enter recovery", failure >= 0)
        assertTrue("ChatGPT proxy must inspect launch result inside recovery guard", launch > failure)
        assertTrue("failed ChatGPT launch must call setup recovery", recoveryCall > launch)
        assertTrue("proxy must finish after handing off to setup recovery", finish > recoveryCall)
        assertTrue("setup recovery must route to MainActivity", setupIntent >= 0)
        assertTrue(
            "setup recovery must reuse an existing MainActivity",
            setupFlags > setupIntent
        )
    }

    private fun findSource(relativePath: String): File {
        var current = File(requireNotNull(System.getProperty("user.dir"))).canonicalFile
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
