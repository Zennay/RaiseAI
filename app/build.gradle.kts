import java.util.zip.ZipFile

private val sourceRevisionPattern = Regex("^[0-9a-fA-F]{40}$")

fun normalizeSourceRevisionOverride(raw: String?): String? {
    if (raw == null) return null
    val normalized = raw.trim()
    return if (normalized.matches(sourceRevisionPattern)) {
        normalized.lowercase()
    } else {
        "unknown"
    }
}

fun selectSourceRevision(
    override: String?,
    checkedOutRevision: String?,
    cleanWorkingTree: Boolean
): String {
    if (!cleanWorkingTree || override == "unknown") return "unknown"

    val head = checkedOutRevision
        ?.trim()
        ?.lowercase()
        ?.takeIf { it.matches(sourceRevisionPattern) }
        ?: return "unknown"

    return when {
        override == null -> head
        override == head -> override
        else -> "unknown"
    }
}

fun resolveSourceRevision(projectDir: java.io.File): String {
    return try {
        val override = normalizeSourceRevisionOverride(System.getenv("RAISE_BUILD_REVISION"))

        val (statusCode, statusOutput) = runGit(
            projectDir,
            "status",
            "--porcelain",
            "--untracked-files=normal"
        )
        val cleanWorkingTree = statusCode == 0 && statusOutput.isBlank()
        if (!cleanWorkingTree) {
            return selectSourceRevision(override, null, false)
        }

        val (headCode, headOutput) = runGit(projectDir, "rev-parse", "HEAD")
        val checkedOutRevision = headOutput.takeIf { headCode == 0 }
        selectSourceRevision(override, checkedOutRevision, true)
    } catch (_: Exception) {
        "unknown"
    }
}

fun runGit(projectDir: java.io.File, vararg args: String): Pair<Int, String> {
    val process = ProcessBuilder(listOf("git") + args)
        .directory(projectDir)
        .redirectErrorStream(true)
        .start()
    val output = process.inputStream.bufferedReader().use { it.readText() }.trim()
    return process.waitFor() to output
}

val sourceRevision = resolveSourceRevision(rootDir)

plugins {
    id("com.android.application")
}

android {
    namespace = "nl.zennay.raiseai"
    compileSdk = 35

    defaultConfig {
        applicationId = "nl.zennay.raiseai"
        minSdk = 30
        targetSdk = 35
        versionCode = 20
        versionName = "1.5.3"
        buildConfigField("String", "SOURCE_REVISION", "\"$sourceRevision\"")

        // Target Galaxy Watch reports ro.product.cpu.abi=armeabi-v7a.
        // Keep the browser APK watch-specific instead of producing stale desktop/x86 variants.
        ndk {
            abiFilters += "armeabi-v7a"
        }
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    // Last GeckoView line whose AndroidX dependencies build cleanly with SDK 35.
    implementation("org.mozilla.geckoview:geckoview:139.0.20250609112858")
    testImplementation("junit:junit:4.13.2")
}

val verifySourceRevisionOverridePolicy = tasks.register("verifySourceRevisionOverridePolicy") {
    group = "verification"
    description = "Locks fail-closed handling for explicit source-revision build overrides."

    doLast {
        check(normalizeSourceRevisionOverride(null) == null) {
            "An absent source-revision override must continue to use repository provenance."
        }
        check(normalizeSourceRevisionOverride("A".repeat(40)) == "a".repeat(40)) {
            "A valid explicit source revision must be normalized to lowercase."
        }
        check(normalizeSourceRevisionOverride("  " + "B".repeat(40) + "  ") == "b".repeat(40)) {
            "Surrounding whitespace around a valid source revision must be ignored."
        }
        check(normalizeSourceRevisionOverride("") == "unknown") {
            "An explicitly empty source-revision override must fail closed."
        }
        check(normalizeSourceRevisionOverride("not-a-revision") == "unknown") {
            "A malformed source-revision override must fail closed."
        }

        val head = "c".repeat(40)
        check(selectSourceRevision(null, head, true) == head) {
            "A clean checkout without an override must use exact HEAD."
        }
        check(selectSourceRevision(head, head, true) == head) {
            "A valid explicit override matching HEAD must be accepted."
        }
        check(selectSourceRevision("d".repeat(40), head, true) == "unknown") {
            "A syntactically valid override that does not match HEAD must fail closed."
        }
        check(selectSourceRevision(head, head, false) == "unknown") {
            "A dirty checkout must not emit an exact source revision."
        }
        check(selectSourceRevision(null, "not-a-revision", true) == "unknown") {
            "An invalid checked-out revision must fail closed."
        }
    }
}

tasks.register("verifyEvidenceBuildIdentity") {
    group = "verification"
    description = "Fails unless the evidence-capable build is clean and pinned to the exact checked-out source revision."

    doLast {
        val expected = normalizeSourceRevisionOverride(System.getenv("RAISE_BUILD_REVISION"))
            ?.takeUnless { it == "unknown" }

        check(expected != null) {
            "RAISE_BUILD_REVISION must contain the exact 40-character Git revision for evidence-capable builds."
        }

        val (statusCode, statusOutput) = runGit(rootDir, "status", "--porcelain", "--untracked-files=normal")
        check(statusCode == 0) {
            "Unable to verify Git working-tree state for evidence build: $statusOutput"
        }
        check(statusOutput.isBlank()) {
            "Evidence-capable builds require a clean Git working tree; found local changes:\n$statusOutput"
        }

        val (headCode, headOutput) = runGit(rootDir, "rev-parse", "HEAD")
        val checkedOutRevision = headOutput.trim().lowercase()
        check(headCode == 0 && checkedOutRevision.matches(Regex("^[0-9a-f]{40}$"))) {
            "Unable to resolve exact checked-out Git revision for evidence build: $headOutput"
        }
        check(checkedOutRevision == expected) {
            "Pinned build revision does not match checked-out HEAD: head=$checkedOutRevision expected=$expected"
        }
        check(sourceRevision == expected) {
            "Build source revision mismatch: resolved=$sourceRevision expected=$expected"
        }
        println("Verified clean evidence build revision: $sourceRevision")
    }
}

tasks.register("verifyWatchAbi") {
    group = "verification"
    description = "Fails unless the debug APK contains exactly the Watch ABI armeabi-v7a."

    doLast {
        val apk = layout.buildDirectory.file("outputs/apk/debug/app-debug.apk").get().asFile
        check(apk.isFile) { "Debug APK not found: ${apk.absolutePath}" }

        val abis = mutableSetOf<String>()
        ZipFile(apk).use { zip ->
            val entries = zip.entries()
            val pattern = Regex("""^lib/([^/]+)/.+[.]so$""")
            while (entries.hasMoreElements()) {
                val entry = entries.nextElement()
                pattern.find(entry.name)?.groupValues?.get(1)?.let(abis::add)
            }
        }

        val expected = setOf("armeabi-v7a")
        check(abis == expected) {
            "Wrong APK ABI set: ${abis.sorted()}. Expected exactly ${expected.sorted()}."
        }
        println("Verified Galaxy Watch ABI: ${abis.single()}")
    }
}

tasks.configureEach {
    if (name == "preBuild") {
        dependsOn(verifySourceRevisionOverridePolicy)
    }
    if (name == "assembleDebug") {
        finalizedBy("verifyWatchAbi")
    }
}
