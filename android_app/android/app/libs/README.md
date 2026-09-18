# KalkanCrypt for Android

Mobile P12 signing in Nika Business uses the official KalkanCrypt Java/JCE
provider from the National Certification Authority of Kazakhstan.

Download the official SDK from the NCA developer distribution
(https://www.pki.gov.kz/get-sdk), then place the official Kalkan Android
JAR/AAR in this directory before building the APK, for example:

- `knca_provider_jce_kalkan*.jar` / `kalkancrypt*.jar`
- `kalkancrypt_xmldsig*.jar`
- compatible Apache Santuario `xmlsec*.jar` from the same SDK/example set

The Gradle build automatically packages `*.jar` and `*.aar` files from
`android/app/libs`.

Do not store user P12 files, passwords, or private keys in the repository.
They are selected at runtime on the Android device and are used only locally
for creating the JWS signature.


For IS ESF mobile signing Nika uses:
- raw GOST 34.10-2015 signature + X.509 certificate for invoice/revoke;
- enveloped XMLDSig for the signed authorization ticket.

Keep the KalkanCrypt, kalkancrypt_xmldsig and xmlsec versions compatible with
the same NCA SDK release. Mixing xmlsec versions can cause XML signature errors.
