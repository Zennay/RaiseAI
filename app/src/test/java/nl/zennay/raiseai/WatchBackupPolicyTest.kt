package nl.zennay.raiseai

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element

class WatchBackupPolicyTest {
    private val legacyDomains = setOf("root", "file", "database", "sharedpref", "external")
    private val currentDomains = legacyDomains + setOf(
        "device_root",
        "device_file",
        "device_database",
        "device_sharedpref"
    )

    @Test
    fun manifestDisablesBackupAndPinsBothBackupRuleFormats() {
        val manifest = findFile("src/main/AndroidManifest.xml").readText()

        assertTrue(
            "Watch app must disable Android backup",
            manifest.contains("android:allowBackup=\"false\"")
        )
        assertFalse(
            "Watch app must not silently re-enable Android backup",
            manifest.contains("android:allowBackup=\"true\"")
        )
        assertTrue(
            "Android 12+ must use explicit data extraction rules for D2D transfer",
            manifest.contains("android:dataExtractionRules=\"@xml/backup_rules\"")
        )
        assertTrue(
            "Android 11 must keep explicit legacy full-backup rules",
            manifest.contains("android:fullBackupContent=\"@xml/backup_rules_legacy\"")
        )
    }

    @Test
    fun android12PlusRulesExcludeEveryBackupDomainFromCloudAndDeviceTransfer() {
        val document = parseXml(findFile("src/main/res/xml/backup_rules.xml"))
        assertEquals("data-extraction-rules", document.documentElement.tagName)

        for (sectionName in listOf("cloud-backup", "device-transfer")) {
            val sections = document.getElementsByTagName(sectionName)
            assertEquals("$sectionName must be declared exactly once", 1, sections.length)
            val section = sections.item(0) as Element
            assertEquals(
                "$sectionName must exclude every eligible app-data domain",
                currentDomains,
                excludedDomains(section)
            )
        }
    }

    @Test
    fun android11LegacyRulesExcludeEveryBackupDomain() {
        val document = parseXml(findFile("src/main/res/xml/backup_rules_legacy.xml"))
        assertEquals("full-backup-content", document.documentElement.tagName)
        assertEquals(
            "legacy backup rules must exclude every eligible app-data domain",
            legacyDomains,
            excludedDomains(document.documentElement)
        )
    }

    private fun excludedDomains(parent: Element): Set<String> {
        val excludes = parent.getElementsByTagName("exclude")
        return (0 until excludes.length)
            .map { excludes.item(it) as Element }
            .onEach {
                assertEquals(
                    "all excluded domains must cover their complete root",
                    ".",
                    it.getAttribute("path")
                )
            }
            .map { it.getAttribute("domain") }
            .toSet()
    }

    private fun parseXml(file: File) =
        DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file)

    private fun findFile(relativePath: String): File {
        var current = File(System.getProperty("user.dir")).canonicalFile
        repeat(6) {
            listOf(
                File(current, relativePath),
                File(current, "app/" + relativePath)
            ).firstOrNull(File::isFile)?.let { return it.canonicalFile }
            current = current.parentFile ?: return@repeat
        }
        error("Could not locate " + relativePath + " from " + System.getProperty("user.dir"))
    }
}
