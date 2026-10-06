package nl.zennay.raiseai

import java.net.URI

internal object GatewayEndpointPolicy {
    fun normalize(raw: String?): String? {
        val value = raw?.trim()?.trimEnd('/')?.takeIf { it.isNotBlank() } ?: return null
        val uri = runCatching { URI(value) }.getOrNull() ?: return null

        if (!uri.scheme.equals("https", ignoreCase = true)) return null
        if (uri.host.isNullOrBlank()) return null
        if (uri.userInfo != null || uri.rawQuery != null || uri.rawFragment != null) return null
        if (uri.rawPath.orEmpty().isNotEmpty()) return null
        if (uri.port == 0 || uri.port < -1 || uri.port > 65_535) return null

        return URI(
            "https",
            null,
            uri.host,
            uri.port,
            null,
            null,
            null
        ).toASCIIString()
    }
}
