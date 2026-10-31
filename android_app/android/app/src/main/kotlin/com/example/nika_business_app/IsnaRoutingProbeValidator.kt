package com.example.nika_business_app

import org.w3c.dom.Element
import java.util.UUID

/**
 * This is a ROUTING TEST, not a tax filing. The only permitted
 * FNO_INTEGRATION business data is the exact invalid XML "<root/>".
 * It contains no data, taxpayer or inner taxpayer XMLDSig.
 */
internal object IsnaRoutingProbeValidator {
    private const val BIP = "http://bip.bee.kz/SyncChannel/v10/Types"
    private const val XSI = "http://www.w3.org/2001/XMLSchema-instance"
    private const val XSD = "http://www.w3.org/2001/XMLSchema"
    private const val XMLNS = "http://www.w3.org/2000/xmlns/"

    private fun fail(): Nothing = throw KalkanJwsSigner.SigningException(
        "UNSAFE_FNO_PROBE",
        "Разрешён только запрос проверки маршрута без налоговой формы (<root/>)",
    )

    private fun children(e: Element): List<Element> =
        (0 until e.childNodes.length).mapNotNull { e.childNodes.item(it) as? Element }

    private fun sole(e: Element, name: String): Element {
        val items = children(e)
        if (items.size != 1 || items[0].tagName != name || items[0].namespaceURI != null) fail()
        return items[0]
    }

    private fun noAttrs(e: Element) {
        if (e.attributes.length != 0) fail()
    }

    fun validate(sendMessage: Element) {
        if (sendMessage.namespaceURI != BIP || sendMessage.localName != "SendMessage") fail()
        noAttrs(sendMessage)
        val request = sole(sendMessage, "request")
        noAttrs(request)
        val parts = children(request)
        if (parts.size != 2 || parts[0].tagName != "requestInfo" ||
            parts[1].tagName != "requestData" || parts.any { it.namespaceURI != null }) fail()
        val info = parts[0]
        noAttrs(info)
        val fields = children(info)
        if (fields.size != 4 ||
            fields.map { it.tagName } != listOf("messageId", "serviceId", "messageDate", "sender") ||
            fields.any { it.namespaceURI != null }) fail()
        if (fields[1].textContent != "FNO_INTEGRATION" ||
            fields[2].textContent.isBlank() || fields[2].textContent.length > 70) fail()
        fields.take(3).forEach { noAttrs(it); if (children(it).isNotEmpty()) fail() }
        try { UUID.fromString(fields[0].textContent.trim()) } catch (_: Exception) { fail() }
        val sender = sole(fields[3], "senderId")
        noAttrs(fields[3]); noAttrs(sender)
        if (children(sender).isNotEmpty()) fail()
        val senderId = sender.textContent?.trim() ?: fail()
        if (senderId.length !in 3..128 || senderId == "smartbridge" ||
            senderId == "nika-offline-test" ||
            senderId.any { it.isWhitespace() || it in "<>&'\"" }) fail()

        val data = sole(parts[1], "data")
        noAttrs(parts[1])
        if (children(data).isNotEmpty() ||
            data.textContent != "<root/>" ||
            data.getAttributeNS(XSI, "type") != "xs:string" ||
            data.lookupNamespaceURI("xs") != XSD ||
            data.lookupNamespaceURI("xsi") != XSI) fail()
        for (i in 0 until data.attributes.length) {
            val attr = data.attributes.item(i)
            if (attr.namespaceURI != XMLNS &&
                !(attr.namespaceURI == XSI && attr.localName == "type")) fail()
        }
    }
}
