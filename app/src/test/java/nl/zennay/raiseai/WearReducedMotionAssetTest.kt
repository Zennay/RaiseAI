package nl.zennay.raiseai

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class WearReducedMotionAssetTest {
    @Test
    fun continuousVoiceAnimationsRespectReducedMotionPreference() {
        val css = findAsset("src/main/assets/raiseai_wear/wear.css").readText()
        val listeningAnimation = css.indexOf(
            "html[data-raiseai-state=\"listening\"] .raiseai-orb-ring"
        )
        val sendingAnimation = css.indexOf(
            "html[data-raiseai-state=\"sending\"] #raiseai-voice-orb"
        )
        val mediaStart = css.indexOf("@media (prefers-reduced-motion: reduce)")

        assertTrue("normal listening animation must exist", listeningAnimation >= 0)
        assertTrue("normal sending animation must exist", sendingAnimation >= 0)
        assertTrue(
            "reduced-motion override must follow the normal animation rules",
            mediaStart > listeningAnimation && mediaStart > sendingAnimation
        )

        val reducedMotion = css.substring(mediaStart)
        assertTrue(
            "listening pulse must be disabled for reduced motion",
            reducedMotion.contains("html[data-raiseai-state=\"listening\"] .raiseai-orb-ring")
        )
        assertTrue(
            "sending breathe animation must be disabled for reduced motion",
            reducedMotion.contains("html[data-raiseai-state=\"sending\"] #raiseai-voice-orb")
        )
        assertTrue(
            "reduced-motion overrides must disable animation",
            reducedMotion.contains("animation: none !important;")
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
