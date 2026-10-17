package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HomeLauncherRecoveryContractTest {
    @Test
    fun runtimeLaunchFailureFallsThroughToNextCandidate() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/HomeLauncher.kt"
        ).readText()

        val candidates = source.indexOf("HomeLaunchPolicy.orderedTargets(installedApp != null).any")
        val guardedStart = source.indexOf("runCatching {", candidates)
        val startActivity = source.indexOf("activity.startActivity(intent)", guardedStart)
        val failureResult = source.indexOf(".getOrDefault(false)", startActivity)

        assertTrue("launcher must iterate ordered fallback candidates", candidates >= 0)
        assertTrue("each runtime launch must be guarded", guardedStart > candidates)
        assertTrue("candidate must be started inside the guarded block", startActivity > guardedStart)
        assertTrue(
            "failed candidate must return false so any() continues to the next route",
            failureResult > startActivity
        )
        assertFalse(
            "fallback must not depend on package-visibility resolveActivity preflights",
            source.contains("resolveActivity(")
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
