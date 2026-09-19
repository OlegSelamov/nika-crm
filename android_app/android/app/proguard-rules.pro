# KalkanCrypt is loaded through reflection from KalkanJwsSigner.
# R8 cannot see those references, so keep the provider in release builds.
-keep class kz.gov.pki.** { *; }
-keep interface kz.gov.pki.** { *; }
-dontwarn kz.gov.pki.**

# Keep Java security provider metadata and declared services.
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod
