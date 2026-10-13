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

    fun load(context: Context): GatewaySettings? =
        GatewayProfileReader.read(File(context.filesDir, FILE_NAME))

    fun isConfigured(context: Context): Boolean = load(context) != null
}
