package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class UpgradeWatchRevisionContractTest {
    @Test
    fun explicitBuildRevisionMustMatchCleanCheckedOutHead() {
        val script = findProjectFile("upgrade-watch.command").readText()

        val cleanTree = script.indexOf("Refusing evidence-capable build from a dirty Git worktree.")
        val headResolution = script.indexOf("""checked_out_revision="$(git rev-parse HEAD | tr 'A-F' 'a-f')"""")
        val explicitPresence = script.indexOf("RAISE_BUILD_REVISION+x")
        val malformedReject = script.indexOf(
            "RAISE_BUILD_REVISION must be an exact 40-character Git revision."
        )
        val headMismatchReject = script.indexOf(
            "requested_revision\" = \"\$checked_out_revision\" ] || {"
        )
        val exportRevision = script.indexOf("export RAISE_BUILD_REVISION")

        assertTrue("Dirty-tree refusal must remain before provenance selection", cleanTree >= 0)
        assertTrue("Checked-out HEAD must be resolved explicitly", headResolution > cleanTree)
        assertTrue(
            "The script must distinguish an absent override from an explicitly empty one",
            explicitPresence > headResolution
        )
        assertTrue("Malformed explicit overrides must fail closed", malformedReject > explicitPresence)
        assertTrue(
            "A syntactically valid explicit override must still match checked-out HEAD",
            headMismatchReject > malformedReject
        )
        assertTrue(
            "Only the validated revision may be exported to Gradle",
            exportRevision > headMismatchReject
        )
    }

    private fun findProjectFile(relativePath: String): File {
        var current = File(System.getProperty("user.dir")).canonicalFile
        repeat(8) {
            val candidate = File(current, relativePath)
            if (candidate.isFile) return candidate.canonicalFile
            current = current.parentFile ?: return@repeat
        }
        error("Could not locate " + relativePath + " from " + System.getProperty("user.dir"))
    }
}
