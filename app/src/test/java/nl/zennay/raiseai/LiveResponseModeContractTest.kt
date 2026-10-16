package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The reply arrives asynchronously, so the persisted mode may have changed since Send.
 * This contract catches regressions that bind TTS to the old, captured preference.
 */
class LiveResponseModeContractTest {
    @Test
    fun replyRespectsModeSelectedAfterSending() {
        val fullAnswer = "Dit is een antwoord."
        val modeAtSend = ResponseMode.SHORT_SPOKEN
        val changedBeforeReply = ResponseMode.SILENT
        assertTrue(SpokenReplyPolicy.textFor(modeAtSend, fullAnswer) != null)
        assertTrue(SpokenReplyPolicy.textFor(changedBeforeReply, fullAnswer) == null)
    }

    @Test
    fun runtimeReadsLatestPreferenceInsideReplyUiCallback() {
        val source = listOf(
            File("src/main/java/nl/zennay/raiseai/NativeVoiceActivity.kt"),
            File("app/src/main/java/nl/zennay/raiseai/NativeVoiceActivity.kt")
        ).firstOrNull { it.isFile }?.readText()
            ?: error("NativeVoiceActivity source unavailable for callback contract")
        val replyStart = source.indexOf("lastAnswer = response.answer")
        assertTrue("Reply callback must store the answer", replyStart >= 0)
        val replyEnd = source.indexOf("fallbackButton.visibility = View.GONE", replyStart)
        assertTrue("Reply callback must have an end marker", replyEnd > replyStart)
        val replyCallback = source.substring(replyStart, replyEnd)
        assertTrue(
            "Late response must consult the current mode",
            replyCallback.contains("ResponseModeStore.load(this@NativeVoiceActivity)")
        )
        assertFalse(
            "Mode captured at Send is stale after user presses Mute",
            replyCallback.contains("textFor(prewarmMode,")
        )
    }
}
