package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class AssistantInputPolicyTest {
    @Test fun allowsMeaningfulMultilineText() {
        val message = "Hello\nwatch\tuser"
        assertEquals(message, AssistantInputPolicy.validate(message))
    }

    @Test fun rejectsEmptyOrWhitespaceOnly() {
        for (message in listOf("", "  \n\t ")) {
            assertThrows(IllegalArgumentException::class.java) {
                AssistantInputPolicy.validate(message)
            }
        }
    }

    @Test fun rejectsEmbeddedNulAndNonPrintingControls() {
        for (message in listOf("hello\u0000world", "hello\u0001world")) {
            assertThrows(IllegalArgumentException::class.java) {
                AssistantInputPolicy.validate(message)
            }
        }
    }

    @Test fun countsUtf8BytesRatherThanCharacters() {
        assertEquals("a".repeat(4096), AssistantInputPolicy.validate("a".repeat(4096)))
        assertThrows(IllegalArgumentException::class.java) {
            AssistantInputPolicy.validate("é".repeat(2049))
        }
    }

    @Test fun preservesUserIntentWithoutTrimming() {
        assertEquals("  run lights  ", AssistantInputPolicy.validate("  run lights  "))
    }
}
