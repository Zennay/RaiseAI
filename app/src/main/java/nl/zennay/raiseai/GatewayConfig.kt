package nl.zennay.raiseai

import android.content.Context
import java.util.Properties

data class GatewaySettings(
    val baseUrl: String,
    val token: String
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

        if (!baseUrl.startsWith("https://")) return null
        if (token.length < 32) return null

        return GatewaySettings(baseUrl, token)
    }

    fun isConfigured(context: Context): Boolean = load(context) != null
}
