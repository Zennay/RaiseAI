package nl.zennay.raiseai

import java.io.ByteArrayInputStream
import java.io.File
import java.nio.file.Files
import java.util.Properties

/**
 * Fail-closed loader for the locally provisioned Watch gateway profile.
 *
 * File.length alone is not an enforced read limit: provisioning can replace
 * the file between the size check and opening it. Read at most one byte above
 * the limit and reject a concurrently grown or truncated profile.
 *
 * This class deliberately has no Android Context dependency, so JVM tests can
 * verify the same file-loading path used by the real Watch app.
 */
internal object GatewayProfileReader {
    const val MAX_PROFILE_BYTES = 16_384

    fun read(file: File): GatewaySettings? = try {
        if (!file.isFile || Files.isSymbolicLink(file.toPath()) ||
            file.length() !in 1L..MAX_PROFILE_BYTES.toLong()
        ) {
            null
        } else {
            // InputStream.readNBytes is not available on every supported Wear SDK.
            // Read at most (limit + 1) bytes using the Android-compatible API.
            val buffer = ByteArray(MAX_PROFILE_BYTES + 1)
            val count = file.inputStream().use { stream ->
                var filled = 0
                while (filled < buffer.size) {
                    val read = stream.read(buffer, filled, buffer.size - filled)
                    if (read < 0) break
                    if (read == 0) throw java.io.IOException("No forward progress reading profile")
                    filled += read
                }
                filled
            }
            val bytes = buffer.copyOf(count)
            if (bytes.size !in 1..MAX_PROFILE_BYTES) {
                null
            } else {
                // Properties.load normally silently lets the *last* duplicate
                // key win. Refuse ambiguous profiles, including escaped aliases.
                val properties = object : Properties() {
                    var duplicateKey = false

                    override fun put(key: Any, value: Any): Any? {
                        if (containsKey(key)) duplicateKey = true
                        return super.put(key, value)
                    }
                }
                ByteArrayInputStream(bytes).use(properties::load)
                if (properties.duplicateKey) return null
                GatewaySettingsPolicy.parse(
                    properties.getProperty("url"),
                    properties.getProperty("token"),
                    properties.getProperty("spki_sha256")
                )
            }
        }
    } catch (_: Exception) {
        // A damaged/removed profile is treated as unconfigured, not an
        // uncaught Watch Activity exception or a network request.
        null
    }
}
