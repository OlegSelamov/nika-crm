package com.example.nika_business_app

import android.content.Context
import android.net.Uri
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Provider
import java.security.SecureRandom
import java.security.Security
import java.security.Signature
import java.security.cert.X509Certificate
import java.util.Arrays

/**
 * Локальная подпись платежей Alatau City Bank.
 *
 * Файл PKCS#12 и пароль никогда не покидают Android-устройство.
 * На сервер передаётся только готовая компактная JWS-строка.
 *
 * Криптография ГОСТ 2015 выполняется официальным JCE-провайдером KalkanCrypt
 * НУЦ РК. Бинарный Kalkan JAR не хранится в публичном репозитории Nika и
 * подключается при сборке приложения из android/app/libs.
 */
object KalkanJwsSigner {
    private const val HEADER_ALG = "ECGOST3410-2015-512"
    private const val SIGNING_ALGORITHM = "ECGOST3410-2015-512"
    private const val SIGNING_OID = "1.2.398.3.10.1.1.2.3.2"

    class SigningException(val code: String, message: String, cause: Throwable? = null) :
        Exception(message, cause)

    fun signAlatauJws(
        context: Context,
        keyUri: Uri,
        passwordChars: CharArray,
        payload: String,
    ): Map<String, Any?> {
        if (payload.isBlank()) {
            throw SigningException("EMPTY_PAYLOAD", "Нет данных платежа для подписи")
        }
        if (passwordChars.isEmpty()) {
            throw SigningException("EMPTY_PASSWORD", "Введите пароль ЭЦП")
        }

        val provider = loadKalkanProvider()

        try {
            val keyStore = KeyStore.getInstance("PKCS12", provider)
            val input = context.contentResolver.openInputStream(keyUri)
                ?: throw SigningException("P12_OPEN_FAILED", "Не удалось открыть выбранный файл ЭЦП")
            input.use {
                try {
                    keyStore.load(it, passwordChars)
                } catch (error: Exception) {
                    throw SigningException(
                        "P12_PASSWORD_OR_FORMAT",
                        "Не удалось открыть ЭЦП. Проверьте пароль и файл .p12",
                        error,
                    )
                }
            }

            val alias = findSigningAlias(keyStore)
                ?: throw SigningException("P12_NO_KEY", "В файле ЭЦП не найден закрытый ключ")

            val privateKey = try {
                keyStore.getKey(alias, passwordChars) as? PrivateKey
            } catch (error: Exception) {
                throw SigningException(
                    "P12_PASSWORD_OR_KEY",
                    "Не удалось получить закрытый ключ. Проверьте пароль ЭЦП",
                    error,
                )
            } ?: throw SigningException("P12_NO_PRIVATE_KEY", "В ЭЦП отсутствует закрытый ключ")

            val certificate = keyStore.getCertificate(alias) as? X509Certificate
                ?: throw SigningException("P12_NO_CERTIFICATE", "В ЭЦП не найден сертификат")

            try {
                certificate.checkValidity()
            } catch (error: Exception) {
                throw SigningException(
                    "CERTIFICATE_NOT_VALID",
                    "Срок действия выбранной ЭЦП истёк или ещё не начался",
                    error,
                )
            }

            val encodedHeader = base64Url(buildHeader(certificate).toByteArray(StandardCharsets.UTF_8))
            val encodedPayload = base64Url(payload.toByteArray(StandardCharsets.UTF_8))
            val signingInput = "$encodedHeader.$encodedPayload".toByteArray(StandardCharsets.US_ASCII)

            val signature = createSignature(provider)
            try {
                signature.initSign(privateKey)
                signature.update(signingInput)
            } catch (error: Exception) {
                throw SigningException(
                    "SIGN_INIT_FAILED",
                    "Эта ЭЦП не поддерживает ГОСТ 34.10-2015 512 для платежей Alatau",
                    error,
                )
            }

            val signatureBytes = try {
                signature.sign()
            } catch (error: Exception) {
                throw SigningException("SIGN_FAILED", "Не удалось подписать платёж ЭЦП", error)
            }

            // В примерах Business API подпись ECGOST3410-2015-512 занимает 128 байт.
            // Если Kalkan вернул другой формат, не отправляем потенциально неверный JWS в банк.
            if (signatureBytes.size != 128) {
                throw SigningException(
                    "UNEXPECTED_SIGNATURE_FORMAT",
                    "Kalkan вернул подпись неожиданного формата (${signatureBytes.size} байт вместо 128)",
                )
            }

            val content = "$encodedHeader.$encodedPayload.${base64Url(signatureBytes)}"
            return mapOf(
                "content" to content,
                "certificateSubject" to certificate.subjectX500Principal.name,
                "certificateSerial" to certificate.serialNumber.toString(16).uppercase(),
                "certificateNotBefore" to certificate.notBefore.time,
                "certificateNotAfter" to certificate.notAfter.time,
                "algorithm" to HEADER_ALG,
            )
        } finally {
            Arrays.fill(passwordChars, '\u0000')
        }
    }

    private fun findSigningAlias(keyStore: KeyStore): String? {
        val aliases = keyStore.aliases()
        var fallback: String? = null
        while (aliases.hasMoreElements()) {
            val alias = aliases.nextElement()
            if (!keyStore.isKeyEntry(alias)) continue
            if (fallback == null) fallback = alias

            val cert = keyStore.getCertificate(alias) as? X509Certificate ?: continue
            val keyUsage = cert.keyUsage
            if (keyUsage == null || (keyUsage.isNotEmpty() && keyUsage[0])) {
                return alias
            }
        }
        return fallback
    }

    private fun buildHeader(certificate: X509Certificate): String {
        val x5c = JSONArray().put(
            Base64.encodeToString(certificate.encoded, Base64.NO_WRAP)
        )
        val header = JSONObject()
        header.put("spanid", randomHex(32))
        header.put("cty", "application/json")
        header.put("typ", "JOSE")
        header.put("alg", HEADER_ALG)
        header.put("ts", System.currentTimeMillis().toString())
        header.put("x5c", x5c)
        return header.toString()
    }

    private fun createSignature(provider: Provider): Signature {
        val names = listOf(
            SIGNING_ALGORITHM,
            "GOST3411-2015withECGOST3410-2015-512",
            SIGNING_OID,
        )
        var lastError: Exception? = null
        for (name in names) {
            try {
                return Signature.getInstance(name, provider)
            } catch (error: Exception) {
                lastError = error
            }
        }
        throw SigningException(
            "GOST2015_NOT_AVAILABLE",
            "В KalkanCrypt не найден алгоритм ECGOST3410-2015-512",
            lastError,
        )
    }

    private fun loadKalkanProvider(): Provider {
        Security.getProvider("KALKAN")?.let { return it }

        val classNames = listOf(
            "kz.gov.pki.kalkan.jce.provider.KalkanProvider",
            "kz.gov.pki.kalkan.provider.KalkanProvider",
        )
        var lastError: Throwable? = null

        for (className in classNames) {
            try {
                val clazz = Class.forName(className)
                val provider = clazz.getDeclaredConstructor().newInstance() as Provider
                Security.getProvider(provider.name)?.let { return it }
                Security.addProvider(provider)
                return provider
            } catch (error: Throwable) {
                lastError = error
            }
        }

        throw SigningException(
            "KALKAN_NOT_INSTALLED",
            "В сборке Nika Business отсутствует KalkanCrypt НУЦ РК. Добавьте официальный Kalkan JAR в android/app/libs и пересоберите приложение.",
            lastError,
        )
    }

    private fun base64Url(bytes: ByteArray): String =
        Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)

    private fun randomHex(byteCount: Int): String {
        val bytes = ByteArray(byteCount)
        SecureRandom().nextBytes(bytes)
        return buildString(byteCount * 2) {
            for (byte in bytes) append("%02x".format(byte.toInt() and 0xff))
        }
    }
}
