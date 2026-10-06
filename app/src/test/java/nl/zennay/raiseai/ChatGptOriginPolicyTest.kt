package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatGptOriginPolicyTest {
    @Test
    fun acceptsOnlyHttpsChatGptOrigins() {
        listOf(
            "https://chatgpt.com/",
            "https://chat.openai.com/",
            "https://auth.chatgpt.com/login",
            "https://foo.chat.openai.com/path"
        ).forEach { value ->
            assertTrue("expected trusted origin: " + value, ChatGptOriginPolicy.isTrusted(value))
        }
    }

    @Test
    fun rejectsHttpAndLookalikeHosts() {
        listOf(
            "http://chatgpt.com/",
            "https://chatgpt.com.evil.example/",
            "https://evilchatgpt.com/",
            "https://chat.openai.com.evil.example/",
            "https://chatgpt.com@evil.example/"
        ).forEach { value ->
            assertFalse("expected rejected origin: " + value, ChatGptOriginPolicy.isTrusted(value))
        }
    }

    @Test
    fun rejectsMalformedOrHostlessValues() {
        listOf(
            "",
            "not a url",
            "javascript:alert(1)",
            "file:///tmp/chatgpt.html"
        ).forEach { value ->
            assertFalse("expected rejected value: " + value, ChatGptOriginPolicy.isTrusted(value))
        }
    }

    @Test
    fun hostMatchingIsCaseInsensitive() {
        assertTrue(ChatGptOriginPolicy.isTrusted("HTTPS://CHATGPT.COM/"))
    }
}
