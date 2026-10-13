package nl.zennay.raiseai

import java.io.ByteArrayInputStream
import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.util.Properties

/**
 * Bounded fail-closed reader for the locally provisioned Watch gateway.
 *
 * Checking a file's length is insufficient: it may grow, shrink or be
 * replaced by a symlink before it is opened. Refuse links both at the
 * regular-file check and at open, and reject inconsistent read lengths.
 *
 * Android-free so the actual Watch file-loading path is testable on the JVM.
 */
internal object GatewayProfileReader {
    const val MAX_PROFILE_BYTES = 16_384

    fun read(file: File): GatewaySettings? {
        return try {
            val path = file.toPath()
            if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) return null

            val expectedLength = Files.size(path)
            if (expectedLength !in 1L..MAX_PROFILE_BYTES.toLong()) return null

            // The minimum supported Wear SDK supports Files.newInputStream
            // with NOFOLLOW_LINKS and ordinary InputStream.read.
            val buffer = ByteArray(MAX_PROFILE_BYTES + 1)
            val count = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS).use { stream ->
                var filled = 0
                while (filled < buffer.size) {
                    val read = stream.read(buffer, filled, buffer.size - filled)
                    if (read < 0) break
                    if (read == 0) throw java.io.IOException("No progress reading gateway profile")
                    filled += read
                }
                filled
            }

            // A concurrently truncated/extended profile is ambiguous.
            if (count !in 1..MAX_PROFILE_BYTES ||
                count.toLong() != expectedLength ||
                Files.size(path) != expectedLength
            ) return null

            // The stock Properties parser silently prefers the last
            // duplicate key. Detect aliases after its escaping rules.
            val properties = object : Properties() {
                var duplicateKey = false

                override fun put(key: Any, value: Any): Any? {
                    if (containsKey(key)) duplicateKey = true
                    return super.put(key, value)
                }
            }
            ByteArrayInputStream(buffer, 0, count).use(properties::load)
            if (properties.duplicateKey) return null

            GatewaySettingsPolicy.parse(
                properties.getProperty("url"),
                properties.getProperty("token"),
                properties.getProperty("spki_sha256")
            )
        } catch (_: Exception) {
            // Damaged, missing or unreadable settings must not crash the UI.
            null
        }
    }
}
