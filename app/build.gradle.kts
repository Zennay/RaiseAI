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
        versionCode = 13
        versionName = "1.3.0"

        // Galaxy Watch 7 uses arm64. Shipping only that GeckoView binary keeps the APK
        // far smaller than Mozilla's three-architecture AAR.
        ndk {
            abiFilters += "arm64-v8a"
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