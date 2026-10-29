package com.example.nika_business_app

import android.util.Base64
import org.json.JSONObject
import org.w3c.dom.Element
import org.xml.sax.InputSource
import java.io.ByteArrayInputStream
import java.io.StringReader
import java.security.Provider
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Very narrow, LOCAL-ONLY test for the provider's real FNO_INTEGRATION wire shape.
 *
 * It deliberately signs an invalid FNO code (000.00), fake sender, and a single
 * fixed marker. There is no network call, no taxpayer data, and no production
 * signing entrypoint. The inner XMLDSig is verified BEFORE transport signing.
 */
internal object IsnaOfflineFnoValidator {
    private const val DS = "http://www.w3.org/2000/09/xmldsig#"
    private const val XSI = "http://www.w3.org/2001/XMLSchema-instance"
    private const val XSD = "http://www.w3.org/2001/XMLSchema"
    private const val XMLNS = "http://www.w3.org/2000/xmlns/"
    private const val SIGNATURE_URI =
        "urn:ietf:params:xml:ns:pkigovkz:xmlsec:algorithms:gostr34102015-gostr34112015-512"
    private const val DIGEST_URI =
        "urn:ietf:params:xml:ns:pkigovkz:xmlsec:algorithms:gostr34112015-512"

    private fun fail(step: String = "недопустимый SOAP"): Nothing =
        throw KalkanJwsSigner.SigningException(
            "NON_DEMO_SOAP",
            "Пробная ФНО не прошла локальную проверку: $step",
        )

    // Android DOM implementations may place namespace declarations on either
    // element during signing. We validate their resolved URIs, not their count.
    private fun onlyNamespaceAttributes(element: Element): Boolean {
        for (index in 0 until element.attributes.length) {
            val attr = element.attributes.item(index)
            if (attr.namespaceURI != "http://www.w3.org/2000/xmlns/") return false
        }
        return true
    }

    private fun children(parent: Element): List<Element> =
        (0 until parent.childNodes.length).mapNotNull { parent.childNodes.item(it) as? Element }

    private fun names(obj: JSONObject): Set<String> {
        val names = mutableSetOf<String>()
        val iterator = obj.keys()
        while (iterator.hasNext()) names.add(iterator.next())
        return names
    }

    private fun expectOne(parent: Element, tag: String): Element {
        val list = children(parent)
        if (list.size != 1 || list[0].tagName != tag || list[0].namespaceURI != null) fail()
        return list[0]
    }

    fun validate(sendMessage: Element, provider: Provider) {
        if (sendMessage.localName != "SendMessage" ||
            sendMessage.namespaceURI != "http://bip.bee.kz/SyncChannel/v10/Types") fail()
        val request = expectOne(sendMessage, "request")
        val requestParts = children(request)
        if (requestParts.map { it.tagName } != listOf("requestInfo", "requestData") ||
            requestParts.any { it.namespaceURI != null }) fail()
        val info = requestParts[0]
        val parts = children(info)
        if (parts.map { it.tagName } != listOf("messageId", "serviceId", "messageDate", "sender") ||
            parts.any { it.namespaceURI != null }) fail()
        if (parts[0].textContent.isNullOrBlank() ||
            parts[1].textContent != "FNO_INTEGRATION" ||
            parts[2].textContent.isNullOrBlank()) fail()
        val sender = expectOne(parts[3], "senderId")
        if (sender.textContent != "nika-fno-offline-only") fail()

        val data = expectOne(requestParts[1], "data")
        if (data.getAttributeNS(XSI, "type") != "xs:string" ||
            data.lookupNamespaceURI("xs") != XSD ||
            data.lookupNamespaceURI("xsi") != XSI ||
            children(data).isNotEmpty()) fail("вложенный SOAP data")
        for (index in 0 until data.attributes.length) {
            val attr = data.attributes.item(index)
            if (attr.namespaceURI != XMLNS &&
                !(attr.namespaceURI == XSI && attr.localName == "type")) {
                fail("неожиданные атрибуты data")
            }
        }
        val signedFno = data.textContent ?: fail()
        if (signedFno.length > 100_000 || signedFno.contains("<!DOCTYPE", true) ||
            signedFno.contains("<!ENTITY", true)) fail()

        val factory = DocumentBuilderFactory.newInstance()
        factory.isNamespaceAware = true
        factory.isExpandEntityReferences = false
        // Match KalkanJwsSigner.parseXml(): some Android parsers do not
        // implement every optional feature. DOCTYPE and ENTITY were already
        // rejected *before* parsing, and expansion is disabled.
        for ((feature, enabled) in listOf(
            "http://apache.org/xml/features/disallow-doctype-decl" to true,
            "http://xml.org/sax/features/external-general-entities" to false,
            "http://xml.org/sax/features/external-parameter-entities" to false,
            "http://apache.org/xml/features/nonvalidating/load-external-dtd" to false,
        )) {
            try { factory.setFeature(feature, enabled) } catch (_: Throwable) { }
        }
        val doc = try {
            factory.newDocumentBuilder().parse(InputSource(StringReader(signedFno)))
        } catch (_: Exception) {
            fail()
        }
        val root = doc.documentElement
        if (root.tagName != "root" || root.namespaceURI != null ||
            !onlyNamespaceAttributes(root)) fail("внутренний root")
        val innerParts = children(root)
        if (innerParts.size != 2 || innerParts[0].tagName != "data" ||
            innerParts[0].namespaceURI != null ||
            innerParts[1].localName != "Signature" || innerParts[1].namespaceURI != DS) fail()
        val plain = innerParts[0]
        if (!onlyNamespaceAttributes(plain) || children(plain).isNotEmpty())
            fail("содержимое внутреннего data")
        val json = try { JSONObject(plain.textContent) } catch (_: Exception) { fail() }
        if (names(json) != setOf("code", "fnoDto") ||
            json.optString("code") != "000.00") fail()
        val dto = json.optJSONObject("fnoDto") ?: fail()
        if (names(dto) != setOf("nikaOfflineDemo") ||
            dto.opt("nikaOfflineDemo") != true) fail()

        val dsig = innerParts[1]
        val signedInfo = dsig.getElementsByTagNameNS(DS, "SignedInfo")
        val signatures = dsig.getElementsByTagNameNS(DS, "SignatureValue")
        val certs = dsig.getElementsByTagNameNS(DS, "X509Certificate")
        val refs = dsig.getElementsByTagNameNS(DS, "Reference")
        if (signedInfo.length != 1 || signatures.length != 1 || certs.length != 1 ||
            refs.length != 1 || signatures.item(0).textContent.isNullOrBlank()) fail()
        val ref = refs.item(0) as? Element ?: fail()
        if (ref.getAttribute("URI") != "") fail()
        val methods = dsig.getElementsByTagNameNS(DS, "SignatureMethod")
        val digests = dsig.getElementsByTagNameNS(DS, "DigestMethod")
        if (methods.length != 1 || digests.length != 1 ||
            (methods.item(0) as Element).getAttribute("Algorithm") != SIGNATURE_URI ||
            (digests.item(0) as Element).getAttribute("Algorithm") != DIGEST_URI) fail()

        // Verify the embedded XMLDSig using its public X.509 certificate.
        // This does NOT establish trust/issuer validity; it does detect tampering.
        val certificate = try {
            val der = Base64.decode(certs.item(0).textContent.replace(Regex("\\s+"), ""), Base64.DEFAULT)
            CertificateFactory.getInstance("X.509")
                .generateCertificate(ByteArrayInputStream(der)) as X509Certificate
        } catch (_: Exception) { fail("сертификат XMLDSig") }
        val xmlSignatureClass = Class.forName("org.apache.xml.security.signature.XMLSignature")
        val signature = xmlSignatureClass
            .getConstructor(Element::class.java, String::class.java).newInstance(dsig, "")
        val valid = xmlSignatureClass
            .getMethod("checkSignatureValue", X509Certificate::class.java)
            .invoke(signature, certificate) as? Boolean
        if (valid != true) {
            throw KalkanJwsSigner.SigningException(
                "INNER_FNO_SIGNATURE_INVALID",
                "Внутренняя подпись пробной ФНО не прошла проверку на Android",
            )
        }
    }
}
