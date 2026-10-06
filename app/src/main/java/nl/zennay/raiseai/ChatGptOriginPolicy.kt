package nl.zennay.raiseai

import java.net.URI
import java.util.Locale

internal object ChatGptOriginPolicy {
    fun isTrusted(value: String): Boolean = runCatching {
        val uri = URI(value)
        val host = uri.host?.lowercase(Locale.ROOT) ?: return@runCatching false
        val https = uri.scheme?.equals("https", ignoreCase = true) == true

        https && (
            host == "chatgpt.com" ||
                host.endsWith(".chatgpt.com") ||
                host == "chat.openai.com" ||
                host.endsWith(".chat.openai.com")
            )
    }.getOrDefault(false)
}
