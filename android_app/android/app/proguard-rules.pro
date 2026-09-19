# KalkanCrypt is loaded through reflection from KalkanJwsSigner.
# R8 cannot see those references, so keep the provider in release builds.
-keep class kz.gov.pki.** { *; }
-keep interface kz.gov.pki.** { *; }
-dontwarn kz.gov.pki.**

# Keep Java security provider metadata and declared services.
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod


# Kalkan XMLDSig uses Apache Santuario through reflection.
-keep class org.apache.xml.security.** { *; }
-keep interface org.apache.xml.security.** { *; }

# Android ESF signing uses the DOM path only; desktop StAX APIs are optional.
-dontwarn javax.xml.stream.**
