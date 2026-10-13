package nl.zennay.raiseai

import java.net.URI
import java.net.URISyntaxException

/**
 * Validate the locally provisioned gateway before constructing a request URL.
 *
 * The Watch client appends /v1/assistant to baseUrl, so a configured URL must
 * be a single HTTPS origin, not a URL with path, credentials, query or fragment.
 * All invalid input is treated as unconfigured rather than being sent to the
 * network. This helper has no Android dependencies and can run in JVM tests.
 */
internal object GatewaySettingsPolicy {
    fun parse(rawUrl: String?, rawToken: String?, rawPin: String?): GatewaySettings? {
        val url = rawUrl?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        val token = rawToken?.trim()?.takeIf { it.length >= 32 } ?: return null

        // Header values must never contain embedded whitespace/control bytes.
        if (token.any { it.isWhitespace() || it.isISOControl() }) return null

        val origin = try {
            URI(url)
        } catch (_: URISyntaxException) {
            return null
        }

        if (origin.scheme != "https" ||
            origin.host.isNullOrBlank() ||
            origin.rawUserInfo != null ||
            origin.rawQuery != null ||
            origin.rawFragment != null ||
            (origin.rawPath != null && origin.rawPath != "" && origin.rawPath != "/") ||
            (origin.port != -1 && origin.port !in 1..65535) ||
            origin.isOpaque
        ) return null

        val rawPinValue = rawPin?.trim().orEmpty()
        val pin = if (rawPinValue.isEmpty()) null
                  else PinnedTls.normalizePin(rawPinValue) ?: return null

        return GatewaySettings(url.trimEnd('/'), token, pin)
    }
}
