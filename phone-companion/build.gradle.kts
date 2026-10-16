plugins {
    id("com.android.application") version "9.4.0"
}

android {
    namespace = "nl.zennay.raiseai.phone"
    compileSdk = 35

    defaultConfig {
        applicationId = "nl.zennay.raiseai"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}
