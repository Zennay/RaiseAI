package nl.zennay.raiseai

import org.junit.Assert.*
import org.junit.Test

class ReplyDisplayPolicyTest {
    @Test fun emptyAndOnlyControlsAreNotDisplayed() {
        assertNull(ReplyDisplayPolicy.forWatch(null))
        assertNull(ReplyDisplayPolicy.forWatch("  "))
        assertNull(ReplyDisplayPolicy.forWatch("\u202E\u0000"))
    }

    @Test fun plainUnicodeAndLayoutArePreserved() {
        assertEquals("Hallo 😀\nwereld", ReplyDisplayPolicy.forWatch("  Hallo 😀\nwereld  "))
        assertEquals("regel\t2", ReplyDisplayPolicy.forWatch("regel\t2"))
    }

    @Test fun bidiOverridesAndControlsCannotReachWatchText() {
        assertEquals("abcxyz", ReplyDisplayPolicy.forWatch("abc\u202E\u2066\u200D\u0000xyz"))
        assertEquals("AB", ReplyDisplayPolicy.forWatch("A\uFFFFB"))
    }

    @Test fun textIsBoundedByCodePointsNotUtf16Units() {
        val input = "😀".repeat(ReplyDisplayPolicy.MAX_CODE_POINTS + 1)
        val output = ReplyDisplayPolicy.forWatch(input)!!
        assertEquals(ReplyDisplayPolicy.MAX_CODE_POINTS + 1, output.codePointCount(0, output.length))
        assertTrue(output.endsWith("…"))
        assertEquals("😀".repeat(ReplyDisplayPolicy.MAX_CODE_POINTS) + "…", output)
    }

    @Test fun shortResponseIsNotTruncated() {
        assertEquals("ok", ReplyDisplayPolicy.forWatch("ok"))
        assertEquals("<b>not html</b>", ReplyDisplayPolicy.forWatch("<b>not html</b>"))
    }

    @Test fun trailingUnsafeCharactersDoNotForceTruncation() {
        assertEquals("x".repeat(ReplyDisplayPolicy.MAX_CODE_POINTS),
            ReplyDisplayPolicy.forWatch("x".repeat(ReplyDisplayPolicy.MAX_CODE_POINTS) + "\u202E"))
    }
}
