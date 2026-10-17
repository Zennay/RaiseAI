import java.util.zip.ZipFile

private val sourceRevisionPattern = Regex("^[0-9a-fA-F]{40}$")

fun resolveSourceRevision(projectDir: java.io.File): String {
    return try {
        val override = System.getenv("RAISE_BUILD_REVISION")
            ?.trim()
            ?.takeIf { it.matches(sourceRevisionPattern) }
        if (override != null) return override.lowercase()

        val statusProcess = ProcessBuilder("git", "status", "--porcelain", "--untracked-files=normal")
            .directory(projectDir)
            .redirectErrorStream(true)
            .start()
        val status = statusProcess.inputStream.bufferedReader().use { it.readText() }
        if (statusProcess.waitFor() != 0 || status.isNotBlank()) {
            return "unknown"
        }

        val process = ProcessBuilder("git", "rev-parse", "HEAD")
            .directory(projectDir)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }.trim()
        if (process.waitFor() == 0 && output.matches(sourceRevisionPattern)) {
            output.lowercase()
        } else {
            "unknown"
        }
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
        versionCode = 21
        versionName = "1.5.4"
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

tasks.register("verifyEvidenceBuildIdentity") {
    group = "verification"
    description = "Fails unless the evidence-capable build is clean and pinned to the exact checked-out source revision."

    doLast {
        val expected = System.getenv("RAISE_BUILD_REVISION")
            ?.trim()
            ?.lowercase()
            ?.takeIf { it.matches(Regex("^[0-9a-f]{40}$")) }

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
    if (name == "assembleDebug") {
        finalizedBy("verifyWatchAbi")
    }
}
