import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    namespace = "com.example.nika_business_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.nika_business_app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystorePropertiesFile.exists()) {
            create("release") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (keystorePropertiesFile.exists()) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
}

dependencies {
    implementation(fileTree(mapOf(
        "dir" to "libs",
        "include" to listOf("*.jar", "*.aar")
    )))
    implementation("androidx.biometric:biometric:1.1.0")

    // НУЦ РК fork of Auth0 java-jwt with GG2015 support.
    // Kalkan itself is already packaged in app/libs, so do not pull a second provider.
    implementation("kz.gov.pki:java-jwt:4.4.0") {
        exclude(group = "kz.gov.pki.kalkan", module = "knca_provider_jce_kalkan")
    }

    // Kalkan XMLDSig 0.5.x / JSR-105 1.2.1 use Apache Santuario 3.0.2.
    // Keep it non-transitive on Android to avoid pulling desktop StAX/Woodstox deps.
    implementation("org.apache.santuario:xmlsec:3.0.2") {
        isTransitive = false
    }
    implementation("org.slf4j:slf4j-api:2.0.9")
    implementation("javax.xml.crypto:jsr105-api:1.0.1")
    implementation("commons-codec:commons-codec:1.15")
}

flutter {
    source = "../.."
}
