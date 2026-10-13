package nl.zennay.raiseai

import android.content.Context
import java.io.File
import java.util.Properties

data class GatewaySettings(
    val baseUrl: String,
    val token: String,
    val spkiSha256: String? = null
)

object GatewayConfig {
    private const val FILE_NAME = "raise-gateway.properties"
    private const val MAX_SETTINGS_BYTES = 16_384L

    fun load(context: Context): GatewaySettings? {
        val file = File(context.filesDir, FILE_NAME)
        // Local configuration is untrusted input. Do not let malformed, unreadable
        // or oversized settings crash the Watch assistant entry point.
        return try {
            if (!file.isFile || file.length() !in 1L..MAX_SETTINGS_BYTES) return null

            val properties = Properties()
            file.inputStream().use(properties::load)
            GatewaySettingsPolicy.parse(
                properties.getProperty("url"),
                properties.getProperty("token"),
                properties.getProperty("spki_sha256")
            )
        } catch (_: Exception) {
            null
        }
    }

    fun isConfigured(context: Context): Boolean = load(context) != null
}
