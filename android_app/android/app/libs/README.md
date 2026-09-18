# KalkanCrypt for Android

Mobile P12 signing in Nika Business uses the official KalkanCrypt Java/JCE
provider from the National Certification Authority of Kazakhstan.

Place the official Kalkan Android JAR/AAR from the NCA SDK in this directory
before building the APK, for example:

- `knca_provider_jce_kalkan*.jar`

The Gradle build automatically packages `*.jar` and `*.aar` files from
`android/app/libs`.

Do not store user P12 files, passwords, or private keys in the repository.
They are selected at runtime on the Android device and are used only locally
for creating the JWS signature.
