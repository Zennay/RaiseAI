package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeVoiceLifecycleContractTest {
    @Test
    fun speechRecognizerStartupIsFailClosed() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/NativeVoiceActivity.kt"
        ).readText()

        val start = source.indexOf("private fun startListening()")
        val end = source.indexOf("private fun scopedRecognitionListener", start)
        assertTrue("startListening must exist", start >= 0)
        assertTrue("scoped listener must follow startListening", end > start)

        val startListening = source.substring(start, end)
        assertTrue(
            "SpeechRecognizer creation must be guarded",
            startListening.contains("val nextRecognizer = runCatching {")
        )
        assertTrue(
            "SpeechRecognizer startListening must be guarded",
            startListening.contains("nextRecognizer.startListening(intent)")
        )
        assertTrue(
            "startup failures must use the user-visible fallback state",
            startListening.contains("showError(\"Spraakherkenning kon niet starten\")")
        )
        assertTrue(
            "failed startup must invalidate the recognizer generation",
            startListening.contains("recognitionSessions.invalidate(recognitionGeneration)")
        )
    }

    @Test
    fun asynchronousOutcomeGateRequiresStartedUiAndClosesOnStop() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/NativeVoiceActivity.kt"
        ).readText()

        val onStart = source.substring(
            source.indexOf("override fun onStart()"),
            source.indexOf("override fun onStop()")
        )
        val onStop = source.substring(
            source.indexOf("override fun onStop()"),
            source.indexOf("override fun onRequestPermissionsResult")
        )
        val postGate = source.substring(
            source.indexOf("private fun postToUiIfActive"),
            source.indexOf("private fun setState")
        )

        assertTrue("onStart must open UI delivery", onStart.contains("isUiStarted = true"))
        assertTrue("onStop must close UI delivery", onStop.contains("isUiStarted = false"))
        assertTrue(
            "async outcomes must be rejected before posting while UI is stopped",
            postGate.contains("if (!isUiStarted) return")
        )
        assertTrue(
            "async outcomes must be rechecked on the main thread",
            postGate.contains("if (isUiStarted && !isFinishing && !isDestroyed)")
        )
    }

    @Test
    fun asynchronousGatewayOutcomeIsRecordedOnlyInsideActiveUiDelivery() {
        val source = findSource(
            "src/main/java/nl/zennay/raiseai/NativeVoiceActivity.kt"
        ).readText()
        val submitStart = source.indexOf("private fun submit(text: String)")
        val postGateStart = source.indexOf("private fun postToUiIfActive", submitStart)
        assertTrue("gateway submit path must exist", submitStart >= 0)
        assertTrue("UI delivery gate must follow gateway submit path", postGateStart > submitStart)

        val gatewaySource = source.substring(submitStart, postGateStart)
        assertOutcomeWriteIsLifecycleGated(
            source = gatewaySource,
            blockStart = ".onSuccess { response ->",
            blockEnd = ".onFailure { error ->",
            evidenceWrite = "WatchE2eEvidence.recordSuccess("
        )
        assertOutcomeWriteIsLifecycleGated(
            source = gatewaySource,
            blockStart = ".onFailure { error ->",
            blockEnd = null,
            evidenceWrite = "WatchE2eEvidence.recordFailure("
        )
    }

    private fun assertOutcomeWriteIsLifecycleGated(
        source: String,
        blockStart: String,
        blockEnd: String?,
        evidenceWrite: String
    ) {
        val start = source.indexOf(blockStart)
        assertTrue("expected gateway outcome block: $blockStart", start >= 0)

        val end = if (blockEnd == null) {
            source.length
        } else {
            source.indexOf(blockEnd, start + blockStart.length)
        }
        assertTrue(
            "expected gateway outcome block end: " + (blockEnd ?: "<scope end>"),
            end > start
        )

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
