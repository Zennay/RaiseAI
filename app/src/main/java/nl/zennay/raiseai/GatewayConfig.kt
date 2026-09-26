package nl.zennay.raiseai

import android.content.Context
import java.util.Properties

data class GatewaySettings(
    val baseUrl: String,
    val token: String,
    val spkiSha256: String? = null
)

object GatewayConfig {
    private const val FILE_NAME = "raise-gateway.properties"

    fun load(context: Context): GatewaySettings? {
        val file = context.filesDir.resolve(FILE_NAME)
        if (!file.isFile) return null

        val properties = Properties()
        file.inputStream().use(properties::load)

        val baseUrl = properties.getProperty("url")?.trim()?.trimEnd('/') ?: return null
        val token = properties.getProperty("token")?.trim() ?: return null
        val rawPin = properties.getProperty("spki_sha256")?.trim().orEmpty()
        val pin = if (rawPin.isBlank()) null else PinnedTls.normalizePin(rawPin) ?: return null

        if (!baseUrl.startsWith("https://")) return null
        if (token.length < 32) return null

        return GatewaySettings(baseUrl, token, pin)
    }

    fun isConfigured(context: Context): Boolean = load(context) != null
}