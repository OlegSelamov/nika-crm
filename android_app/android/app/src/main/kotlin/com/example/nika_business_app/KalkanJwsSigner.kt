package com.example.nika_business_app

import android.content.Context
import android.net.Uri
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import org.w3c.dom.Document
import java.io.ByteArrayInputStream
import java.io.StringWriter
import java.nio.charset.StandardCharsets
import java.security.Key
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Provider
import java.security.SecureRandom
import java.security.Security
import java.security.Signature
import java.security.cert.X509Certificate
import java.util.Arrays
import javax.xml.parsers.DocumentBuilderFactory
import javax.xml.transform.OutputKeys
import javax.xml.transform.TransformerFactory
import javax.xml.transform.dom.DOMSource
import javax.xml.transform.stream.StreamResult

/**
 * Единый мобильный криптомодуль Nika Business.
 *
 * PKCS#12 и пароль используются только локально на Android.
 * На сервер уходят только готовые подписи/сертификат.
 */
object KalkanJwsSigner {
    private const val HEADER_ALG = "ECGOST3410-2015-512"
    private const val SIGNING_ALGORITHM = "ECGOST3410-2015-512"
    private const val SIGNING_OID = "1.2.398.3.10.1.1.2.3.2"

    private const val XML_SIGNATURE_URI =
        "urn:ietf:params:xml:ns:pkigovkz:xmlsec:algorithms:gostr34102015-gostr34112015-512"
    private const val XML_DIGEST_URI =
        "urn:ietf:params:xml:ns:pkigovkz:xmlsec:algorithms:gostr34112015-512"
    private const val XML_C14N_URI =
        "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
    private const val XML_ENVELOPED_URI =
        "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

    class SigningException(val code: String, message: String, cause: Throwable? = null) :
        Exception(message, cause)

    fun capabilities(): Map<String, Any?> {
        val providerClass = listOf(
            "kz.gov.pki.kalkan.jce.provider.KalkanProvider",
            "kz.gov.pki.kalkan.provider.KalkanProvider",
        ).firstOrNull { className ->
            try {
                Class.forName(className)
                true
            } catch (_: Throwable) {
                false
            }
        }

        val xmlAvailable = try {
            Class.forName("org.apache.xml.security.signature.XMLSignature")
            true
        } catch (_: Throwable) {
            false
        }

        return mapOf(
            "kalkanInstalled" to (providerClass != null),
            "providerClass" to providerClass,
            "xmlSignatureInstalled" to xmlAvailable,
            "readyForAlatau" to (providerClass != null),
            "readyForEsfRaw" to (providerClass != null),
            "readyForEsfXml" to (providerClass != null && xmlAvailable),
        )
    }

    private data class KeyMaterial(
        val provider: Provider,
        val privateKey: PrivateKey,
        val certificate: X509Certificate,
    )

    fun signAlatauJws(
        context: Context,
        keyUri: Uri,
        passwordChars: CharArray,
        payload: String,
    ): Map<String, Any?> {
        if (payload.isBlank()) throw SigningException("EMPTY_PAYLOAD", "Нет данных платежа для подписи")
        val material = loadKeyMaterial(context, keyUri, passwordChars)
        try {
            val encodedHeader = base64Url(buildHeader(material.certificate).toByteArray(StandardCharsets.UTF_8))
            val encodedPayload = base64Url(payload.toByteArray(StandardCharsets.UTF_8))
            val signingInput = "$encodedHeader.$encodedPayload".toByteArray(StandardCharsets.US_ASCII)
            val signatureBytes = signBytes(material, signingInput)

            if (signatureBytes.size != 128) {
                throw SigningException(
                    "UNEXPECTED_SIGNATURE_FORMAT",
                    "Kalkan вернул подпись неожиданного формата (${signatureBytes.size} байт вместо 128)",
                )
            }

            return certificateResult(material.certificate) + mapOf(
                "content" to "$encodedHeader.$encodedPayload.${base64Url(signatureBytes)}",
                "algorithm" to HEADER_ALG,
            )
        } finally {
            Arrays.fill(passwordChars, '\u0000')
        }
    }

    /**
     * Формат соответствует текущему NCALayer basics.sign(format=raw, decode=false,
     * outputCert=true): Base64 подпись + X.509 сертификат отдельным полем.
     */
    fun signEsfRaw(
        context: Context,
        keyUri: Uri,
        passwordChars: CharArray,
        payload: String,
    ): Map<String, Any?> {
        if (payload.isBlank()) throw SigningException("EMPTY_PAYLOAD", "Нет данных ЭСФ для подписи")
        val material = loadKeyMaterial(context, keyUri, passwordChars)
        try {
            val signatureBytes = signBytes(material, payload.toByteArray(StandardCharsets.UTF_8))
            val signature = Base64.encodeToString(signatureBytes, Base64.NO_WRAP)
            val certificate = Base64.encodeToString(material.certificate.encoded, Base64.NO_WRAP)

            return certificateResult(material.certificate) + mapOf(
                "signature" to signature,
                "certificate" to certificate,
                "algorithm" to SIGNING_ALGORITHM,
            )
        } finally {
            Arrays.fill(passwordChars, '\u0000')
        }
    }

    /**
     * XMLDSig для тикета авторизации ИС ЭСФ.
     *
     * Использует официальный kalkancrypt_xmldsig + Apache Santuario из SDK НУЦ.
     * В коде нет compile-time зависимости: библиотеки подхватываются из app/libs
     * и вызываются reflection, поэтому обычная Flutter-сборка не ломается,
     * если SDK ещё не добавлен.
     */
    fun signEsfXml(
        context: Context,
        keyUri: Uri,
        passwordChars: CharArray,
        payload: String,
    ): Map<String, Any?> {
        if (payload.isBlank()) throw SigningException("EMPTY_PAYLOAD", "Нет XML для подписи")
        val material = loadKeyMaterial(context, keyUri, passwordChars)
        try {
            val document = parseXml(payload)
            initializeXmlSecurity(material.provider)
            val signedXml = signXmlDocument(document, material.privateKey, material.certificate)
            return certificateResult(material.certificate) + mapOf(
                "signedXml" to signedXml,
                "certificate" to Base64.encodeToString(material.certificate.encoded, Base64.NO_WRAP),
                "algorithm" to XML_SIGNATURE_URI,
            )
        } finally {
            Arrays.fill(passwordChars, '\u0000')
        }
    }

    private fun loadKeyMaterial(
        context: Context,
        keyUri: Uri,
        passwordChars: CharArray,
    ): KeyMaterial {
        if (passwordChars.isEmpty()) throw SigningException("EMPTY_PASSWORD", "Введите пароль ЭЦП")
        val provider = loadKalkanProvider()
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

        return KeyMaterial(provider, privateKey, certificate)
    }

    private fun signBytes(material: KeyMaterial, bytes: ByteArray): ByteArray {
        val signature = createSignature(material.provider)
        try {
            signature.initSign(material.privateKey)
            signature.update(bytes)
            return signature.sign()
        } catch (error: Exception) {
            throw SigningException("SIGN_FAILED", "Не удалось сформировать ЭЦП", error)
        }
    }

    private fun parseXml(payload: String): Document {
        try {
            val factory = DocumentBuilderFactory.newInstance()
            factory.isNamespaceAware = true
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false)
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false)
            return factory.newDocumentBuilder().parse(
                ByteArrayInputStream(payload.toByteArray(StandardCharsets.UTF_8))
            )
        } catch (error: Exception) {
            throw SigningException("INVALID_XML", "ИС ЭСФ передала некорректный XML для подписи", error)
        }
    }

    private fun initializeXmlSecurity(provider: Provider) {
        try {
            System.setProperty(
                "org.apache.xml.security.resource.config",
                "/kz/gov/pki/kalkan/xmldsig/pkigovkz.xml",
            )
            val initClass = Class.forName("org.apache.xml.security.Init")
            initClass.getMethod("init").invoke(null)

            val mapperClass = Class.forName("org.apache.xml.security.algorithms.JCEMapper")
            mapperClass.getMethod("setProviderId", String::class.java)
                .invoke(null, provider.name)
        } catch (error: Throwable) {
            throw SigningException(
                "KALKAN_XMLDSIG_NOT_INSTALLED",
                "Для мобильной авторизации ИС ЭСФ добавьте из SDK НУЦ библиотеки kalkancrypt_xmldsig, kalkancrypt и совместимый Apache xmlsec в android/app/libs.",
                error,
            )
        }
    }

    private fun signXmlDocument(
        document: Document,
        privateKey: PrivateKey,
        certificate: X509Certificate,
    ): String {
        try {
            val xmlSignatureClass = Class.forName("org.apache.xml.security.signature.XMLSignature")
            val transformsClass = Class.forName("org.apache.xml.security.transforms.Transforms")

            val xmlSignature = xmlSignatureClass
                .getConstructor(
                    Document::class.java,
                    String::class.java,
                    String::class.java,
                    String::class.java,
                )
                .newInstance(document, "", XML_SIGNATURE_URI, XML_C14N_URI)

            val signatureElement = xmlSignatureClass.getMethod("getElement").invoke(xmlSignature)
                as org.w3c.dom.Node
            document.documentElement.appendChild(signatureElement)

            val transforms = transformsClass
                .getConstructor(Document::class.java)
                .newInstance(document)
            transformsClass.getMethod("addTransform", String::class.java)
                .invoke(transforms, XML_ENVELOPED_URI)

            xmlSignatureClass
                .getMethod(
                    "addDocument",
                    String::class.java,
                    transformsClass,
                    String::class.java,
                )
                .invoke(xmlSignature, "", transforms, XML_DIGEST_URI)

            xmlSignatureClass.getMethod("addKeyInfo", X509Certificate::class.java)
                .invoke(xmlSignature, certificate)
            xmlSignatureClass.getMethod("sign", Key::class.java)
                .invoke(xmlSignature, privateKey)

            val transformer = TransformerFactory.newInstance().newTransformer()
            transformer.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "no")
            transformer.setOutputProperty(OutputKeys.ENCODING, "UTF-8")
            val writer = StringWriter()
            transformer.transform(DOMSource(document), StreamResult(writer))
            return writer.toString()
        } catch (error: SigningException) {
            throw error
        } catch (error: Throwable) {
            throw SigningException(
                "XML_SIGN_FAILED",
                "Не удалось сформировать XML-подпись ИС ЭСФ. Проверьте версии Kalkan XMLDSig и Apache xmlsec из одного комплекта SDK НУЦ.",
                error,
            )
        }
    }

    private fun certificateResult(certificate: X509Certificate): Map<String, Any?> = mapOf(
        "certificateSubject" to certificate.subjectX500Principal.name,
        "certificateSerial" to certificate.serialNumber.toString(16).uppercase(),
        "certificateNotBefore" to certificate.notBefore.time,
        "certificateNotAfter" to certificate.notAfter.time,
    )

    private fun findSigningAlias(keyStore: KeyStore): String? {
        val aliases = keyStore.aliases()
        var fallback: String? = null
        while (aliases.hasMoreElements()) {
            val alias = aliases.nextElement()
            if (!keyStore.isKeyEntry(alias)) continue
            if (fallback == null) fallback = alias
            val cert = keyStore.getCertificate(alias) as? X509Certificate ?: continue
            val keyUsage = cert.keyUsage
            if (keyUsage == null || (keyUsage.isNotEmpty() && keyUsage[0])) return alias
        }
        return fallback
    }

    private fun buildHeader(certificate: X509Certificate): String {
        val header = JSONObject()
        header.put("spanid", randomHex(32))
        header.put("cty", "application/json")
        header.put("typ", "JOSE")
        header.put("alg", HEADER_ALG)
        header.put("ts", System.currentTimeMillis().toString())
        header.put(
            "x5c",
            JSONArray().put(Base64.encodeToString(certificate.encoded, Base64.NO_WRAP)),
        )
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
