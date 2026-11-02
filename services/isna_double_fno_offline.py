"""Strict offline-only verification of the two Android signatures on a fake FNO.

This never creates or files a declaration. The only allowed inner payload is
{"code":"000.00","fnoDto":{"nikaOfflineDemo":true}} and the only sender
is the literal nika-fno-offline-only. No network call, DB write or key load.
Outer SOAP and inner signed XML must each verify independently on TEST VPS.
"""
from __future__ import annotations

import base64
import hashlib
import os
import binascii
import json
import re
import xml.etree.ElementTree as ET

from scripts.isna_inspect_wss import (
    SOAP, BIP, DS, WSSE, WSU, GOST_SIGNATURE, GOST_DIGEST, EXC_C14N,
    InvalidSoap, extract_signer_certificate, q,
)
from services.isna_vps_signature_verifier import (
    verify_soap_signature_on_vps, verify_inner_fno_signature_on_vps,
)

MAX_DOUBLE_SOAP_BYTES = 256_000
DEMO_SENDER = "nika-fno-offline-only"
DEMO_MESSAGE_ID = "00000000-0000-4000-8000-000000000001"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
XML_C14N_INCLUSIVE = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
XML_C14N_INCL_COMMENTS = XML_C14N_INCLUSIVE + "#WithComments"
XML_ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
INNER_DIGEST_TRANSFORMS = (XML_ENVELOPED, XML_C14N_INCL_COMMENTS)


def reject(message: str) -> None:
    raise InvalidSoap("Unsafe offline double-signature sample: " + message)


def single_element(parent: ET.Element, tag: str) -> ET.Element:
    children = list(parent)
    if len(children) != 1 or children[0].tag != tag:
        reject("unexpected element")
    return children[0]


def unique_child(parent: ET.Element, tag: str) -> ET.Element:
    matches = parent.findall(tag)
    if len(matches) != 1:
        reject("missing/duplicate child")
    return matches[0]


def signature_info(signature: ET.Element, expected_uri: str, *,
                   expected_c14n: str | tuple[str, ...],
                   expected_transforms: tuple[str, ...]) -> None:
    info = unique_child(signature, q(DS, "SignedInfo"))
    ref = unique_child(info, q(DS, "Reference"))
    if len(info.findall(q(DS, "Reference"))) != 1 or ref.get("URI") != expected_uri:
        reject("bad XMLDSig reference")
    methods = info.findall(q(DS, "SignatureMethod"))
    canonical = info.findall(q(DS, "CanonicalizationMethod"))
    digest = ref.findall(q(DS, "DigestMethod"))
    transforms = ref.findall(q(DS, "Transforms"))
    actual_c14n = canonical[0].get("Algorithm") if len(canonical) == 1 else None
    allowed_c14n = (expected_c14n,) if isinstance(expected_c14n, str) else expected_c14n
    if (len(methods) != 1 or methods[0].get("Algorithm") != GOST_SIGNATURE
        or actual_c14n not in allowed_c14n
        or len(digest) != 1 or digest[0].get("Algorithm") != GOST_DIGEST
        or len(transforms) != 1
        or tuple(t.get("Algorithm") for t in transforms[0]) != expected_transforms
        or len(signature.findall(q(DS, "SignatureValue"))) != 1
        or not (signature.findtext(q(DS, "SignatureValue")) or "").strip()
        or len(ref.findall(q(DS, "DigestValue"))) != 1):
        reject("unsupported signature algorithm or transform")
    if any(t.attrib != {"Algorithm": alg} or len(t)
           for t, alg in zip(list(transforms[0]), expected_transforms)):
        reject("unexpected transform attributes")


def inspect_offline_double_soap(soap_xml: str) -> tuple[str, bytes]:
    """Return the verbatim decoded inner XML and the outer public cert.

    This is a syntactic, not cryptographic check. Signature bytes stay intact.
    """
    if not isinstance(soap_xml, str) or not soap_xml:
        reject("empty document")
    if len(soap_xml.encode("utf-8")) > MAX_DOUBLE_SOAP_BYTES:
        reject("SOAP exceeds size limit")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", soap_xml, re.I):
        reject("DTD forbidden")
    try:
        root = ET.fromstring(soap_xml.encode("utf-8"))
    except ET.ParseError:
        reject("malformed SOAP")
    if root.tag != q(SOAP, "Envelope") or len(root) != 2:
        reject("not SOAP 1.1")
    header, body = list(root)
    if header.tag != q(SOAP, "Header") or body.tag != q(SOAP, "Body"):
        reject("SOAP ordering")
    sec = single_element(header, q(WSSE, "Security"))
    outer_sig = single_element(sec, q(DS, "Signature"))
    body_id = body.get(q(WSU, "Id"))
    if not body_id or not re.fullmatch(r"id-fno-offline-[A-Za-z0-9-]{4,80}", body_id):
        reject("unexpected Body ID")
    if len(root.findall(".//" + q(DS, "Signature"))) != 1:
        reject("multiple outer XMLDSig elements")
    signature_info(outer_sig, "#" + body_id,
                   expected_c14n=EXC_C14N, expected_transforms=(EXC_C14N,))
    public_cert, profile = extract_signer_certificate(root)
    if profile != "key-identifier":
        reject("WSSE KeyIdentifier required")

    operation = single_element(body, q(BIP, "SendMessage"))
    request = single_element(operation, "request")
    parts = list(request)
    if len(parts) != 2 or [p.tag for p in parts] != ["requestInfo", "requestData"]:
        reject("unexpected request fields")
    info, data_wrapper = parts
    info_fields = list(info)
    if [p.tag for p in info_fields] != ["messageId", "serviceId", "messageDate", "sender"]:
        reject("unexpected metadata")
    if ((info_fields[0].text or "") != DEMO_MESSAGE_ID
        or (info_fields[1].text or "") != "FNO_INTEGRATION"
        or not (info_fields[2].text or "").strip()):
        reject("unexpected service or message")
    sender = single_element(info_fields[3], "senderId")
    if (sender.text or "") != DEMO_SENDER or sender.attrib:
        reject("real sender is forbidden")
    data = single_element(data_wrapper, "data")
    if data.attrib != {q(XSI, "type"): "xs:string"} or list(data):
        reject("nested payload must be xs:string")
    if any(x.attrib for x in (operation, request, info, data_wrapper)):
        reject("additional request attributes")
    inner_xml = data.text or ""
    if (len(inner_xml.encode("utf-8")) > 120_000
        or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", inner_xml, re.I)):
        reject("unsafe inner XML")
    try:
        fno = ET.fromstring(inner_xml.encode("utf-8"))
    except ET.ParseError:
        reject("malformed inner XML")
    if fno.tag != "root" or fno.attrib or len(fno) != 2:
        reject("not a fixed offline FNO")
    payload, inner_sig = list(fno)
    if (payload.tag != "data" or payload.attrib or len(payload)
        or inner_sig.tag != q(DS, "Signature")):
        reject("inner layout invalid")
    if len(fno.findall(".//" + q(DS, "Signature"))) != 1:
        reject("multiple inner signatures")
    try:
        sample = json.loads(payload.text or "")
    except (ValueError, TypeError):
        reject("invalid sample JSON")
    if sample != {"code": "000.00", "fnoDto": {"nikaOfflineDemo": True}}:
        reject("real taxpayer data or FNO code forbidden")
    signature_info(inner_sig, "", expected_c14n=(XML_C14N_INCLUSIVE, XML_C14N_INCL_COMMENTS),
                   expected_transforms=INNER_DIGEST_TRANSFORMS)
    key_info = unique_child(inner_sig, q(DS, "KeyInfo"))
    x509_data = single_element(key_info, q(DS, "X509Data"))
    cert_node = single_element(x509_data, q(DS, "X509Certificate"))
    if cert_node.attrib or len(cert_node) or not (cert_node.text or "").strip():
        reject("missing inner public certificate")
    try:
        inner_cert = base64.b64decode(re.sub(r"\s+", "", cert_node.text or ""), validate=True)
    except (ValueError, binascii.Error):
        reject("invalid inner X509")
    if not 3 <= len(inner_cert) <= 65536 or inner_cert[0] != 0x30:
        reject("invalid inner X509 size")
    return inner_xml, public_cert


def extract_taxpayer_public_cert(inner_xml: str) -> bytes:
    """Read the *already structurally allowlisted* inner signer X.509 DER.

    This never opens a P12 or trusts the embedded cert as an authority.
    The cryptographic check is performed by a separate isolated worker.
    """
    try:
        inner = ET.fromstring(inner_xml.encode("utf-8"))
        signature = unique_child(inner, q(DS, "Signature"))
        key_info = unique_child(signature, q(DS, "KeyInfo"))
        x509_data = single_element(key_info, q(DS, "X509Data"))
        cert_text = single_element(x509_data, q(DS, "X509Certificate")).text or ""
        return base64.b64decode(re.sub(r"\s+", "", cert_text), validate=True)
    except (ET.ParseError, ValueError, binascii.Error):
        reject("unreadable inner signing certificate")


def compare_certificate_roles(inner_cert: bytes, outer_cert: bytes) -> dict:
    """Report certificate identity; NEVER mistake identity for permission.

    An optional server-side SHA-256 PIN must refer to the *registered*
    information-system transport cert, not the taxpayer's public cert.
    Missing PIN is reported as unknown, not matched.
    """
    inner_hash = hashlib.sha256(inner_cert).hexdigest().upper()
    outer_hash = hashlib.sha256(outer_cert).hexdigest().upper()
    pinned = (os.getenv("ISNA_BIP_REGISTERED_CERT_SHA256") or "").strip().replace(":", "").upper()
    if pinned and not re.fullmatch(r"[A-F0-9]{64}", pinned):
        reject("invalid configured transport certificate fingerprint")
    return {
        "taxpayerCertSha256": inner_hash,
        "transportCertSha256": outer_hash,
        "sameCertificateUsed": inner_hash == outer_hash,
        "transportCertPinConfigured": bool(pinned),
        "transportCertMatchesConfiguredPin": outer_hash == pinned if pinned else None,
        "taxpayerAuthorityChecked": False,
        "governmentCertificateAccepted": None,
    }


def verify_offline_double_soap(soap_xml: str) -> dict:
    inner_xml, outer_cert = inspect_offline_double_soap(soap_xml)
    certificate_roles = compare_certificate_roles(extract_taxpayer_public_cert(inner_xml), outer_cert)
    # Independent native calls. A valid outer signature does NOT imply a
    # valid inner signature, and vice versa. Neither unlocks gateway POST.
    outer = verify_soap_signature_on_vps(soap_xml, outer_cert)
    inner = verify_inner_fno_signature_on_vps(inner_xml)
    return {
        "structureOk": True,
        "sampleType": "invalid-fno-000.00-offline-double",
        **certificate_roles,
        "certificateProfile": "key-identifier",
        "outerCryptoVerified": outer["cryptoVerifiedOnServer"] is True,
        "outerVerificationStatus": outer["cryptoVerificationStatus"],
        "outerNativeCode": outer.get("cryptoNativeCode"),
        "innerCryptoVerified": inner["cryptoVerifiedOnServer"] is True,
        "innerVerificationStatus": inner["cryptoVerificationStatus"],
        "innerNativeCode": inner.get("cryptoNativeCode"),
        "bothVerified": outer["cryptoVerifiedOnServer"] is True and inner["cryptoVerifiedOnServer"] is True,
        "offlineOnly": True,
        "gatewayContacted": False,
        "filingCreated": False,
    }
