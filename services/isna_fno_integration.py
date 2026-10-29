"""TEST-first FNO_INTEGRATION payload adapter for Smart Bridge.

Based on provider-supplied FNO_INTEGRATION request and response samples.
Only builds/parses XML offline. It NEVER sends requests or performs an EDS
signature. A document MUST be signed independently by its taxpayer, then the
outer SOAP Body separately signed by Nika's transport GOST certificate.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from services.isna_bip import (
    BIP_TYPES_NS, SOAP_NS, IsnaBipError, build_sync_envelope,
)

DS_NS = "http://www.w3.org/2000/09/xmldsig#"
FNO_SERVICE_ID = "FNO_INTEGRATION"
MAX_FNO_BYTES = 5_000_000


def _safe_parse(xml: str, what: str) -> ET.Element:
    if not isinstance(xml, str) or not xml.strip():
        raise IsnaBipError(f"{what}: empty XML.")
    if len(xml.encode("utf-8")) > MAX_FNO_BYTES:
        raise IsnaBipError(f"{what}: XML exceeds 5 MB.")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise IsnaBipError(f"{what}: DTD/ENTITY declarations are prohibited.")
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise IsnaBipError(f"{what}: not well-formed XML.") from exc


def inspect_taxpayer_signed_fno(xml: str) -> dict[str, Any]:
    """Structural preflight. Does NOT cryptographically verify XMLDSig.

    FNO example: <root><data>JSON string</data><ds:Signature>...</ds:Signature>
    A bad CDATA terminator or an unsigned JSON document must fail closed.
    Taxpayer codes, names and tax values are never printed or returned.
    """
    root = _safe_parse(xml, "Signed FNO")
    if root.tag != "root":
        raise IsnaBipError("Signed FNO: unqualified <root> is required.")
    children = list(root)
    if len(children) != 2 or children[0].tag != "data" or children[1].tag != f"{{{DS_NS}}}Signature":
        raise IsnaBipError("Signed FNO: expected <data> followed by ds:Signature.")
    if len(list(children[0])):
        raise IsnaBipError("Signed FNO: inner data must contain JSON text.")
    signature = children[1]
    signed_info = signature.find(f"{{{DS_NS}}}SignedInfo")
    signature_value = signature.find(f"{{{DS_NS}}}SignatureValue")
    if signed_info is None or signature_value is None or not (signature_value.text or "").strip():
        raise IsnaBipError("Signed FNO: XMLDSig SignedInfo/SignatureValue missing.")
    refs = signed_info.findall(f"{{{DS_NS}}}Reference")
    if len(refs) != 1 or refs[0].get("URI") not in ("", None):
        raise IsnaBipError("Signed FNO: unexpected XMLDSig Reference.")
    try:
        data = json.loads((children[0].text or "").strip())
    except json.JSONDecodeError as exc:
        raise IsnaBipError("Signed FNO: inner data is not valid JSON.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("code"), str) or not isinstance(data.get("fnoDto"), dict):
        raise IsnaBipError("Signed FNO: JSON requires code and fnoDto object.")
    return {
        "format_ok": True,
        "form_code": data["code"],
        "xml_signature_present": True,
        "cryptographic_signature_verified": False,
    }


def build_fno_integration_soap(
    signed_fno_xml: str,
    *,
    sender_id: str,
    sender_password: str = "",
    message_id: str | None = None,
) -> str:
    """Create unsigned transport SOAP, with FNO as xs:string (NO network).

    Before use, verify taxpayer's inner XMLDSig through a trusted Kalkan
    verifier. This structural check alone is NOT authorization to file taxes.
    After construction, sign the entire SOAP Body with WS-Security GOST.
    """
    inspect_taxpayer_signed_fno(signed_fno_xml)
    if not isinstance(sender_id, str) or not sender_id.strip():
        raise IsnaBipError("Registered Smart Bridge senderId is required.")
    if sender_id.strip().lower() == "smartbridge":
        raise IsnaBipError("The example senderId 'smartbridge' is not a Nika credential.")
    return build_sync_envelope(
        signed_fno_xml,
        service_id=FNO_SERVICE_ID,
        sender_id=sender_id,
        sender_password=sender_password,
        message_id=message_id,
        data_encoding="string",
    )


def parse_fno_integration_response(response_xml: str) -> dict[str, Any]:
    """Parse real response status and business JSON, not HTTP status alone.

    A SOAP 200 response may still be a SOAP Fault, or have status=OK with
    business success=false. Neither case means the FNO was accepted.
    """
    root = _safe_parse(response_xml, "FNO SOAP response")
    if root.tag != f"{{{SOAP_NS}}}Envelope":
        raise IsnaBipError("FNO response: SOAP 1.1 Envelope expected.")
    body = root.find(f"{{{SOAP_NS}}}Body")
    if body is None:
        raise IsnaBipError("FNO response: SOAP Body missing.")
    fault = body.find(f"{{{SOAP_NS}}}Fault")
    if fault is not None:
        return {
            "ok": False,
            "fault": True,
            "status_code": fault.findtext("faultcode") or "",
            "message": fault.findtext("faultstring") or "",
            "fno_id": None,
        }
    operation = body.find(f"{{{BIP_TYPES_NS}}}SendMessageResponse")
    response = operation.find("response") if operation is not None else None
    if response is None:
        raise IsnaBipError("FNO response: SendMessageResponse missing.")
    info = response.find("responseInfo")
    if info is None:
        raise IsnaBipError("FNO response: responseInfo missing.")
    status_code = info.findtext("status/code") or ""
    message = info.findtext("status/message") or ""
    data = response.find("responseData/data")
    payload = None
    if data is not None and (data.text or "").strip():
        try:
            payload = json.loads(data.text)
        except json.JSONDecodeError as exc:
            raise IsnaBipError("FNO response: responseData/data is not valid JSON.") from exc
    successful_business = isinstance(payload, dict) and payload.get("success") is True
    return {
        "ok": status_code == "OK" and successful_business,
        "fault": False,
        "status_code": status_code,
        "message": message,
        "service_success": successful_business,
        "fno_id": payload.get("fno_id") if isinstance(payload, dict) else None,
    }
