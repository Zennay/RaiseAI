package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class GatewayProfileReaderTest {
    @get:Rule val folder = TemporaryFolder()

    private val token = "a".repeat(64)

    private fun write(name: String, content: String): File =
        folder.newFile(name).also { it.writeText(content, Charsets.ISO_8859_1) }

    @Test fun loadsProvisionedWatchProfileAndKeepsPin() {
        val file = write(
            "gateway.properties",
            "url=https://watch.example:8443\ntoken=$token\nspki_sha256=${"cd".repeat(32)}\n"
        )
        val settings = GatewayProfileReader.read(file)
        assertNotNull(settings)
        assertEquals("https://watch.example:8443", settings?.baseUrl)
        assertEquals(token, settings?.token)
        assertEquals("cd".repeat(32), settings?.spkiSha256)
    }

    @Test fun symlinkedProfileIsNeverFollowed() {
        val genuine = write("real.properties", "url=https://watch.example\ntoken=$token\n")
        val link = File(folder.root, "shortcut.properties")
        java.nio.file.Files.createSymbolicLink(link.toPath(), genuine.toPath())
        assertNull(GatewayProfileReader.read(link))
    }

    @Test fun missingEmptyOrDirectoryProfilesCannotConfigureWatch() {
        assertNull(GatewayProfileReader.read(File(folder.root, "absent.properties")))
        assertNull(GatewayProfileReader.read(folder.newFile("empty.properties")))
        assertNull(GatewayProfileReader.read(folder.root))
    }

    @Test fun oversizedProfileIsRejectedBeforeParsing() {
        val file = write("large.properties", "url=https://watch.example\ntoken=$token\n" +
            "#".repeat(GatewayProfileReader.MAX_PROFILE_BYTES))
        assertNull(GatewayProfileReader.read(file))
    }

    @Test fun acceptsExactBoundedFileWhenItContainsValidProperties() {
        val prefix = "url=https://watch.example\ntoken=$token\n"
        val padding = "#".repeat(GatewayProfileReader.MAX_PROFILE_BYTES - prefix.length)
        val file = write("boundary.properties", prefix + padding)
        assertEquals(GatewayProfileReader.MAX_PROFILE_BYTES.toLong(), file.length())
        assertEquals("https://watch.example", GatewayProfileReader.read(file)?.baseUrl)
    }

    @Test fun rejectsInvalidUnicodePropertiesEscapeWithoutThrowing() {
        val file = write(
            "corrupt.properties",
            "url=https://watch.example\ntoken=$token\nspki_sha256=\\uNOTHEX\n"
        )
        assertNull(GatewayProfileReader.read(file))
    }

    @Test fun rejectsInvalidOriginOrShortTokenFromDisk() {
        val badUrl = write("bad-url.properties", "url=https://watch.example/evil\ntoken=$token\n")
        val badToken = write("bad-token.properties", "url=https://watch.example\ntoken=short\n")
        assertNull(GatewayProfileReader.read(badUrl))
        assertNull(GatewayProfileReader.read(badToken))
    }

    @Test fun rejectsProfileWithUntrustedLineEndingInBearerToken() {
        val file = write("linebreak.properties", "url=https://watch.example\ntoken=bad\\nheader$token\n")
        assertNull(GatewayProfileReader.read(file))
    }

    @Test fun rejectsUnprovisionedTokenWithoutAccessingNetwork() {
        val file = write("missing-token.properties", "url=https://watch.example\n")
        assertNull(GatewayProfileReader.read(file))
    }
}
