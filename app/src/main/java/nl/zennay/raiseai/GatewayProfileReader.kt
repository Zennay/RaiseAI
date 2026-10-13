package nl.zennay.raiseai

import java.io.ByteArrayInputStream
import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
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
        val path = file.toPath()
        // Both the check and the open must refuse links. A link could replace
        // the file after isRegularFile() unless the open also uses NOFOLLOW.
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            null
        } else {
            val expectedLength = Files.size(path)
            if (expectedLength !in 1L..MAX_PROFILE_BYTES.toLong()) {
                null
            } else {
                // Read at most (limit + 1) bytes on the minimum Wear SDK.
                val buffer = ByteArray(MAX_PROFILE_BYTES + 1)
                val count = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS).use { stream ->
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
                // A concurrently truncated or extended file is ambiguous; do
                // not accept partial settings or quietly ignore appended bytes.
                if (count.toLong() != expectedLength ||
                    count !in 1..MAX_PROFILE_BYTES ||
                    Files.size(path) != expectedLength
                ) {
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
                if (properties.duplicateKey) {
                    null
                } else {
                    GatewaySettingsPolicy.parse(
                        properties.getProperty("url"),
                        properties.getProperty("token"),
                        properties.getProperty("spki_sha256")
                    )
                }
                }
            }
        }
    } catch (_: Exception) {
        // A damaged/removed profile is treated as unconfigured, not an
        // uncaught Watch Activity exception or a network request.
        null
    }
}
