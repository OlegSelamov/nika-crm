package com.example.nika_business_app

import android.content.Context
import android.net.Uri
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import org.w3c.dom.Document
import org.xml.sax.InputSource
import java.io.StringReader
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
    private const val SIGNING_ALGORITHM = "ECGOST3410-2015"
    private const val SIGNING_OID = "1.2.398.3.10.1.1.2.3.2"
    private const val SIGNING_EKU_OID = "1.3.6.1.5.5.7.3.4"
    private const val AUTH_EKU_OID = "1.3.6.1.5.5.7.3.2"
    private const val ORG_EKU_OID = "1.2.398.3.3.4.1.2"
    private const val ORG_HEAD_EKU_OID = "1.2.398.3.3.4.1.2.1"
    private const val ORG_TRUSTED_EKU_OID = "1.2.398.3.3.4.1.2.2"
    private const val ORG_EMPLOYEE_EKU_OID = "1.2.398.3.3.4.1.2.5"

    private const val XML_SIGNATURE_URI =
        "urn:ietf:params:xml:ns:pkigovkz:xmlsec:algorithms:gostr34102015-gostr34112015-512"
    private const val XML_DIGEST_URI =
        "urn:ietf:params:xml:ns:pkigovkz:xmlsec:algorithms:gostr34112015-512"
    private const val XML_C14N_URI =
        "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
    private const val XML_ENVELOPED_URI =
        "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
    private const val XML_C14N_WITH_COMMENTS_URI =
        "http://www.w3.org/TR/2001/REC-xml-c14n-20010315#WithComments"

    class SigningException(val code: String, message: String, cause: Throwable? = null) :
        Exception(message, cause)

    fun capabilities(): Map<String, Any?> {
        val loader = KalkanJwsSigner::class.java.classLoader
        fun classAvailable(name: String): Boolean = try {
            Class.forName(name, false, loader)
            true
        } catch (_: Throwable) {
            false
        }

        val providerClass = listOf(
            "kz.gov.pki.kalkan.jce.provider.KalkanProvider",
            "kz.gov.pki.kalkan.provider.KalkanProvider",
        ).firstOrNull(::classAvailable)

        // Do not initialize Santuario merely to report capabilities. If XMLSecurity
        // gets initialized before KncaXS sets the Kalkan config, Init.init() becomes
        // a no-op later and the GOST XML algorithms remain unregistered.
        val xmlSecurityAvailable =
            classAvailable("org.apache.xml.security.signature.XMLSignature")
        val kalkanXmlDsigAvailable =
            classAvailable("kz.gov.pki.kalkan.xmldsig.DsigConstants")

        return mapOf(
            "kalkanInstalled" to (providerClass != null),
            "providerClass" to providerClass,
            "xmlSecurityInstalled" to xmlSecurityAvailable,
            "kalkanXmlDsigInstalled" to kalkanXmlDsigAvailable,
            "readyForAlatau" to (providerClass != null),
            "readyForEsfRaw" to (providerClass != null),
            "readyForEsfXml" to (providerClass != null && xmlSecurityAvailable && kalkanXmlDsigAvailable),
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
        signingTimestampMs: Long? = null,
    ): Map<String, Any?> {
        if (payload.isBlank()) throw SigningException("EMPTY_PAYLOAD", "Нет данных платежа для подписи")
        val material = loadKeyMaterial(context, keyUri, passwordChars)
        try {
            val timestamp = signingTimestampMs
                ?.takeIf { it > 0L }
                ?: System.currentTimeMillis()
            val encodedHeader = base64Url(
                buildHeader(material.certificate, timestamp)
                    .toByteArray(StandardCharsets.UTF_8)
            )
            val encodedPayload = base64Url(payload.toByteArray(StandardCharsets.UTF_8))
            val signingInput = "$encodedHeader.$encodedPayload".toByteArray(StandardCharsets.US_ASCII)
            val signatureBytes = signBytes(material, signingInput)

            if (signatureBytes.size != 128) {
                throw SigningException(
                    "UNEXPECTED_SIGNATURE_FORMAT",
                    "Kalkan вернул подпись неожиданного формата (${signatureBytes.size} байт вместо 128)",
                )
            }

            // Do not send a JWS that our own Kalkan provider cannot verify.
            // This catches a wrong key/certificate alias or provider-format issue
            // before Alatau turns it into the misleading generic HTTP 424 error.
            val verifier = createSignature(material.provider)
            val locallyValid = try {
                verifier.initVerify(material.certificate.publicKey)
                verifier.update(signingInput)
                verifier.verify(signatureBytes)
            } catch (error: Exception) {
                throw SigningException(
                    "SIGN_VERIFY_FAILED",
                    "Не удалось проверить сформированную банковскую подпись локально",
                    error,
                )
            }
            if (!locallyValid) {
                throw SigningException(
                    "SIGN_VERIFY_FAILED",
                    "Сформированная банковская подпись не прошла локальную проверку",
                )
            }

            return certificateResult(material.certificate) + mapOf(
                "content" to "$encodedHeader.$encodedPayload.${base64Url(signatureBytes)}",
                "algorithm" to HEADER_ALG,
                "signingTimestampMs" to timestamp,
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
            ?: throw SigningException(
                "P12_NO_SIGNING_KEY",
                "В выбранной ЭЦП нет сертификата подписи, подходящего для банковского платежа",
            )

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
        // NCALayer в браузере терпимее к декларации authTicketXml, чем Android Xerces.
        // ИС ЭСФ может вернуть некорректный version="0.0". Для XMLDSig сама
        // декларация не участвует в подписываемом DOM, поэтому удаляем любые XML
        // declarations до разбора, а Transformer при выдаче signedXml создаст
        // корректную декларацию XML 1.0 / UTF-8.
        var xml = payload
            .trimStart('\uFEFF', '\u200B', '\u200E', '\u200F', '\u2060')
            .trim()

        val declarationPattern = Regex(
            """<\?xml\b.*?\?>""",
            setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
        )
        xml = xml.replace(declarationPattern, "").trim()

        if (xml.isEmpty()) {
            throw SigningException("EMPTY_XML", "ИС ЭСФ вернула пустой XML тикета авторизации")
        }

        try {
            val factory = DocumentBuilderFactory.newInstance()
            factory.isNamespaceAware = true

            // Android's built-in JAXP implementation can throw exactly:
            // "This parser does not support specification \"Unknown\" version \"0.0\""
            // when setXIncludeAware(...) is called. That exception was previously
            // caught below and mislabeled as INVALID_XML, although the ESF ticket
            // itself was not the problem. We do not use XInclude here, so do not
            // call setXIncludeAware at all.
            factory.isExpandEntityReferences = false

            // Keep XXE protections, but tolerate parser implementations that do
            // not expose one of these optional features.
            fun safeFeature(name: String, value: Boolean) {
                try {
                    factory.setFeature(name, value)
                } catch (_: Throwable) {
                    // Unsupported optional hardening flag on this Android parser.
                }
            }
            safeFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
            safeFeature("http://xml.org/sax/features/external-general-entities", false)
            safeFeature("http://xml.org/sax/features/external-parameter-entities", false)
            safeFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false)

            val source = InputSource(StringReader(xml))
            return factory.newDocumentBuilder().parse(source)
        } catch (error: Exception) {
            val parserMessage = error.message
                ?.replace(Regex("\\s+"), " ")
                ?.trim()
                ?.take(220)
            val message = if (parserMessage.isNullOrBlank()) {
                "ИС ЭСФ передала XML тикета, который не удалось разобрать"
            } else {
                "Не удалось разобрать XML тикета ИС ЭСФ: $parserMessage"
            }
            throw SigningException("INVALID_XML", message, error)
        }
    }

    private fun initializeXmlSecurity(provider: Provider) {
        try {
            // Official Kalkan initialization.
            val kncaXsClass = Class.forName("kz.gov.pki.kalkan.xmldsig.KncaXS")
            kncaXsClass.getMethod("loadXMLSecurity").invoke(null)

            // Android can reach Santuario Init earlier than expected (including via
            // capability probes or another library). Santuario Init is one-shot:
            // once alreadyInitialized=true, KncaXS cannot reload pkigovkz.xml.
            // Therefore explicitly ensure the two Kazakhstan GOST mappings that
            // ESF auth XMLDSig needs. Register calls are idempotent here: an
            // "already registered" error is harmless and intentionally ignored.
            ensureKalkanGostXmlAlgorithms(provider)
        } catch (error: Throwable) {
            var root: Throwable = error
            val visited = HashSet<Throwable>()
            while (root.cause != null && root.cause !== root && visited.add(root)) {
                root = root.cause!!
            }
            val detail = root.message
                ?.replace(Regex("\\s+"), " ")
                ?.trim()
                ?.take(220)
            throw SigningException(
                "KALKAN_XMLDSIG_INIT_FAILED",
                "Не удалось инициализировать Kalkan XMLDSig" +
                    if (detail.isNullOrBlank()) "" else ": $detail",
                error,
            )
        }
    }

    private fun ensureKalkanGostXmlAlgorithms(provider: Provider) {
        // Resource bundle is useful for meaningful xmlsec errors even if the
        // Kalkan config file was only partially loaded on Android.
        try {
            val i18nClass = Class.forName("org.apache.xml.security.utils.I18n")
            i18nClass.getMethod("init", String::class.java, String::class.java)
                .invoke(null, "en", "US")
        } catch (_: Throwable) {
        }

        // Rebuild Santuario's standard registries as well. On some Android
        // processes Init may have become "initialized" before it actually populated
        // every registry. The current symptom is an empty Transform registry
        // ("Unknown transformation ... enveloped-signature").
        fun invokeStaticNoArg(className: String, methodName: String) {
            Class.forName(className).getMethod(methodName).invoke(null)
        }

        invokeStaticNoArg(
            "org.apache.xml.security.transforms.Transform",
            "registerDefaultAlgorithms",
        )
        invokeStaticNoArg(
            "org.apache.xml.security.c14n.Canonicalizer",
            "registerDefaultAlgorithms",
        )
        invokeStaticNoArg(
            "org.apache.xml.security.algorithms.SignatureAlgorithm",
            "registerDefaultAlgorithms",
        )
        invokeStaticNoArg(
            "org.apache.xml.security.algorithms.JCEMapper",
            "registerDefaultAlgorithms",
        )
        invokeStaticNoArg(
            "org.apache.xml.security.utils.resolver.ResourceResolver",
            "registerDefaultResolvers",
        )
        invokeStaticNoArg(
            "org.apache.xml.security.keys.keyresolver.KeyResolver",
            "registerDefaultResolvers",
        )
        try {
            invokeStaticNoArg(
                "org.apache.xml.security.utils.ElementProxy",
                "registerDefaultPrefixes",
            )
        } catch (_: Throwable) {
            // Prefixes may already be registered; this is harmless.
        }

        val signatureAlgorithmClass =
            Class.forName("org.apache.xml.security.algorithms.SignatureAlgorithm")
        try {
            signatureAlgorithmClass
                .getMethod("register", String::class.java, String::class.java)
                .invoke(
                    null,
                    XML_SIGNATURE_URI,
                    "kz.gov.pki.kalkan.xmldsig.algorithms.implementations." +
                        "SignatureBaseGost\$GostR34102015GostR34112015_512",
                )
        } catch (error: Throwable) {
            val causeName = generateSequence(error) { it.cause }
                .map { it.javaClass.simpleName }
                .firstOrNull { it.contains("AlreadyRegistered", ignoreCase = true) }
            if (causeName == null) throw error
        }

        val jceMapperClass = Class.forName("org.apache.xml.security.algorithms.JCEMapper")
        val algorithmClass =
            Class.forName("org.apache.xml.security.algorithms.JCEMapper\$Algorithm")
        val constructor = algorithmClass.getConstructor(
            String::class.java,
            String::class.java,
            String::class.java,
        )
        val registerMethod =
            jceMapperClass.getMethod("register", String::class.java, algorithmClass)

        val digestMapping = constructor.newInstance(
            "",
            "GOST3411-2015-512",
            "MessageDigest",
        )
        registerMethod.invoke(null, XML_DIGEST_URI, digestMapping)

        val signatureMapping = constructor.newInstance(
            "",
            SIGNING_ALGORITHM,
            "Signature",
        )
        registerMethod.invoke(null, XML_SIGNATURE_URI, signatureMapping)

        try {
            jceMapperClass.getMethod("setProviderId", String::class.java)
                .invoke(null, provider.name)
        } catch (_: Throwable) {
        }
    }

    private fun signXmlDocument(
        document: Document,
        privateKey: PrivateKey,
        certificate: X509Certificate,
    ): String {
        var stage = "создание XMLSignature"
        try {
            val xmlSignatureClass = Class.forName("org.apache.xml.security.signature.XMLSignature")
            val transformsClass = Class.forName("org.apache.xml.security.transforms.Transforms")

            // Повторяем рабочую схему NCANode/Kalkan: стандартный 3-аргументный
            // конструктор XMLSignature, затем enveloped + canonicalization transform.
            val xmlSignature = xmlSignatureClass
                .getConstructor(
                    Document::class.java,
                    String::class.java,
                    String::class.java,
                )
                .newInstance(document, "", XML_SIGNATURE_URI)

            stage = "добавление Signature в DOM"
            val signatureElement = xmlSignatureClass.getMethod("getElement").invoke(xmlSignature)
                as org.w3c.dom.Node
            document.documentElement.appendChild(signatureElement)

            stage = "создание transforms"
            val transforms = transformsClass
                .getConstructor(Document::class.java)
                .newInstance(document)
            transformsClass.getMethod("addTransform", String::class.java)
                .invoke(transforms, XML_ENVELOPED_URI)
            transformsClass.getMethod("addTransform", String::class.java)
                .invoke(transforms, XML_C14N_WITH_COMMENTS_URI)

            stage = "добавление Reference"
            xmlSignatureClass
                .getMethod(
                    "addDocument",
                    String::class.java,
                    transformsClass,
                    String::class.java,
                )
                .invoke(xmlSignature, "", transforms, XML_DIGEST_URI)

            stage = "добавление сертификата"
            xmlSignatureClass.getMethod("addKeyInfo", X509Certificate::class.java)
                .invoke(xmlSignature, certificate)

            stage = "криптографическая подпись"
            xmlSignatureClass.getMethod("sign", Key::class.java)
                .invoke(xmlSignature, privateKey)

            stage = "сериализация signed XML"
            val transformer = TransformerFactory.newInstance().newTransformer()
            transformer.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "no")
            transformer.setOutputProperty(OutputKeys.ENCODING, "UTF-8")
            val writer = StringWriter()
            transformer.transform(DOMSource(document), StreamResult(writer))
            return writer.toString()
        } catch (error: SigningException) {
            throw error
        } catch (error: Throwable) {
            var root: Throwable = error
            val visited = HashSet<Throwable>()
            while (root.cause != null && root.cause !== root && visited.add(root)) {
                root = root.cause!!
            }
            val rootMessage = root.message
                ?.replace(Regex("\\s+"), " ")
                ?.trim()
                ?.take(240)
            val detail = buildString {
                append(root.javaClass.simpleName)
                if (!rootMessage.isNullOrBlank()) append(": ").append(rootMessage)
            }
            throw SigningException(
                "XML_SIGN_FAILED",
                "Не удалось сформировать XML-подпись ИС ЭСФ на этапе «$stage». $detail",
                error,
            )
        }
    }

    private fun certificateResult(certificate: X509Certificate): Map<String, Any?> {
        val eku = try {
            certificate.extendedKeyUsage ?: emptyList()
        } catch (_: Exception) {
            emptyList()
        }
        return mapOf(
            "certificateSubject" to certificate.subjectX500Principal.name,
            "certificateSerial" to certificate.serialNumber.toString(16).uppercase(),
            "certificateNotBefore" to certificate.notBefore.time,
            "certificateNotAfter" to certificate.notAfter.time,
            "certificateExtendedKeyUsage" to eku,
            "certificateIsSigning" to (SIGNING_EKU_OID in eku),
            "certificateIsAuthOnly" to (
                AUTH_EKU_OID in eku && SIGNING_EKU_OID !in eku
            ),
        )
    }

    private fun findSigningAlias(keyStore: KeyStore): String? {
        data class Candidate(val alias: String, val score: Int)

        val aliases = keyStore.aliases()
        val candidates = mutableListOf<Candidate>()
        while (aliases.hasMoreElements()) {
            val alias = aliases.nextElement()
            if (!keyStore.isKeyEntry(alias)) continue
            val cert = keyStore.getCertificate(alias) as? X509Certificate ?: continue

            val keyUsage = cert.keyUsage
            val digitalSignature =
                keyUsage == null || (keyUsage.isNotEmpty() && keyUsage[0])
            if (!digitalSignature) continue

            val eku = try {
                cert.extendedKeyUsage ?: emptyList()
            } catch (_: Exception) {
                emptyList()
            }

            // Bank payments must use the EDS signing certificate. Do not silently
            // fall back to an authentication-only key from the same PKCS#12.
            if (SIGNING_EKU_OID !in eku) continue

            var score = 200
            when {
                ORG_HEAD_EKU_OID in eku -> score += 60
                ORG_TRUSTED_EKU_OID in eku -> score += 50
                ORG_EMPLOYEE_EKU_OID in eku -> score += 30
                ORG_EKU_OID in eku -> score += 20
            }

            candidates += Candidate(alias, score)
        }

        return candidates.maxByOrNull { it.score }?.alias
    }

    private fun buildHeader(
        certificate: X509Certificate,
        signingTimestampMs: Long,
    ): String {
        val header = JSONObject()
        header.put("spanid", randomHex(32))
        header.put("cty", "application/json")
        header.put("typ", "JOSE")
        header.put("alg", HEADER_ALG)
        header.put("ts", signingTimestampMs.toString())
        header.put(
            "x5c",
            JSONArray().put(Base64.encodeToString(certificate.encoded, Base64.NO_WRAP)),
        )
        return header.toString()
    }

    private fun createSignature(provider: Provider): Signature {
        val names = listOf(
            // Same JCA algorithm name used by the official NCA java-jwt GG2015 implementation.
            SIGNING_ALGORITHM,
            "ECGOST3410-2015-512",
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
            "В KalkanCrypt не найден алгоритм ECGOST3410-2015",
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
