package nl.zennay.raiseai

import android.content.Context
import java.io.File

data class GatewaySettings(
    val baseUrl: String,
    val token: String,
    val spkiSha256: String? = null
)

object GatewayConfig {
    private const val FILE_NAME = "raise-gateway.properties"

    fun load(context: Context): GatewaySettings? = try {
        GatewayProfileReader.read(File(context.filesDir, FILE_NAME))
    } catch (_: Exception) {
        // Even an inaccessible app files directory must fail as unconfigured.
        null
    }

    fun isConfigured(context: Context): Boolean = load(context) != null
}
