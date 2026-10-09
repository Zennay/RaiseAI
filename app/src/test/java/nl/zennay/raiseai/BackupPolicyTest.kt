package nl.zennay.raiseai

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertEquals
import org.junit.Test
import org.w3c.dom.Element

class BackupPolicyTest {
    private val androidNamespace = "http://schemas.android.com/apk/res/android"
    private val expectedDomains = setOf("root", "file", "database", "sharedpref", "external")

    @Test
    fun manifestDisablesBackupAndReferencesBothRuleFormats() {
        val document = parseProjectXml("src/main/AndroidManifest.xml")
        val application = document.getElementsByTagName("application").item(0) as Element

        assertEquals("false", application.getAttributeNS(androidNamespace, "allowBackup"))
        assertEquals("@xml/backup_rules", application.getAttributeNS(androidNamespace, "fullBackupContent"))
        assertEquals(
            "@xml/data_extraction_rules",
            application.getAttributeNS(androidNamespace, "dataExtractionRules")
        )
    }

    @Test
    fun legacyBackupRulesExcludeEveryPrivateStorageDomain() {
        val document = parseProjectXml("src/main/res/xml/backup_rules.xml")
        assertEquals(expectedDomains, excludedDomains(document.documentElement))
    }

    @Test
    fun android12RulesExcludeCloudAndDeviceTransferData() {
        val document = parseProjectXml("src/main/res/xml/data_extraction_rules.xml")
        listOf("cloud-backup", "device-transfer").forEach { sectionName ->
            val section = document.getElementsByTagName(sectionName).item(0) as Element
            assertEquals(expectedDomains, excludedDomains(section))
        }
    }

    private fun excludedDomains(root: Element): Set<String> {
        val excludes = root.getElementsByTagName("exclude")
        return buildSet {
            for (index in 0 until excludes.length) {
                val element = excludes.item(index) as Element
                assertEquals(".", element.getAttribute("path"))
                add(element.getAttribute("domain"))
            }
        }
    }

    private fun parseProjectXml(relativePath: String) =
        DocumentBuilderFactory.newInstance().apply {
            isNamespaceAware = true
        }.newDocumentBuilder().parse(findProjectFile(relativePath))

    private fun findProjectFile(relativePath: String): File {
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
