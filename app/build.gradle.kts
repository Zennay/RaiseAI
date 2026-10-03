import java.util.zip.ZipFile

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
        versionCode = 17
        versionName = "1.5.0"

        // Target Galaxy Watch reports ro.product.cpu.abi=armeabi-v7a.
        // Keep the browser APK watch-specific instead of producing stale desktop/x86 variants.
        ndk {
            abiFilters += "armeabi-v7a"
        }
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