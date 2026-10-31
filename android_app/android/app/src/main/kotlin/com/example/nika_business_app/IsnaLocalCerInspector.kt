package com.example.nika_business_app

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

/**
 * Reads one PUBLIC X.509 certificate with the Android document picker.
 *
 * The file remains on the user's device. This method never uploads, stores
 * or returns the certificate bytes, and rejects .p12/.pfx/private-key files.
 * Only a SHA-256 fingerprint and validity timestamps are returned to Flutter.
 */
internal object IsnaLocalCerInspector {
    private const val MAX_CERT_BYTES = 65536
    private val ALLOWED_EXTENSIONS = setOf("cer", "crt", "pem", "der")

    fun inspect(context: Context, uri: Uri): Map<String, Any> {
        val filename = context.contentResolver.query(
            uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        } ?: throw IllegalArgumentException(
            "Не удалось узнать имя сертификата. Выберите публичный .cer/.crt/.pem/.der",
        )
        val extension = filename.substringAfterLast('.', "").lowercase()
        if (extension !in ALLOWED_EXTENSIONS) {
            throw IllegalArgumentException(
                "Разрешены только публичные .cer/.crt/.pem/.der. Не выбирайте .p12!",
            )
        }

        val bytes = context.contentResolver.openInputStream(uri)?.use { input ->
            val buffer = ByteArray(4096)
            val output = ByteArrayOutputStream()
            var size = 0
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                size += count
                if (size > MAX_CERT_BYTES) {
                    throw IllegalArgumentException("Слишком большой файл сертификата")
                }
                output.write(buffer, 0, count)
            }
            output.toByteArray()
        } ?: throw IllegalArgumentException("Не удалось открыть публичный сертификат")
        try {
            val cert = CertificateFactory.getInstance("X.509")
                .generateCertificate(ByteArrayInputStream(bytes)) as X509Certificate
            val hash = sha256Fingerprint(cert.encoded)
            return mapOf(
                "sha256" to hash,
                "notBeforeMs" to cert.notBefore.time,
                "notAfterMs" to cert.notAfter.time,
            )
        } catch (_: Exception) {
            throw IllegalArgumentException(
                "Не удалось прочитать X.509 сертификат. Выберите .cer в формате DER или PEM.",
            )
        } finally {
            bytes.fill(0)
        }
    }

    internal fun sha256Fingerprint(der: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(der)
            .joinToString("") { "%02X".format(it.toInt() and 0xFF) }
}
