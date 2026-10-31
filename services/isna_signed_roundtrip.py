"""Offline-only Android -> TEST VPS SOAP diagnostic (never sends to SHÈP).

Accepts ONLY the synthetic Nika server signing sample, which deliberately
uses an invalid serviceId. The VPS optionally performs an INDEPENDENT GOST
verification with xmlsec1; unsupported runtimes explicitly report unverified.
"""
from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET

from scripts.isna_inspect_wss import (
    BIP, DEMO, DS, SOAP, WSSE, InvalidSoap, decode_cert,
    extract_signer_certificate, inspect, q,
)

from services.isna_vps_signature_verifier import verify_soap_signature_on_vps

MAX_DIAGNOSTIC_BYTES = 256_000


def validate_offline_signed_soap(
    soap_xml: str, *, registered_public_cert: bytes | None = None,
) -> dict:
    """Strict structural TEST preflight; no storage, keys or network access.

    The XML contains only a synthetic payload and the signer's PUBLIC X.509.
    The result MUST NOT be interpreted as cryptographic verification or
    government acceptance. No real FNO payload is accepted in this route.
    """
    if not isinstance(soap_xml, str) or not soap_xml.strip():
        raise InvalidSoap("Signed offline SOAP is required.")
    raw = soap_xml.encode("utf-8")
    if len(raw) > MAX_DIAGNOSTIC_BYTES:
        raise InvalidSoap("Signed SOAP exceeds 256 KB offline limit.")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", soap_xml, re.IGNORECASE):
        raise InvalidSoap("DTD/ENTITY are forbidden.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise InvalidSoap("Signed SOAP is malformed XML.") from exc

    embedded, cert_profile = extract_signer_certificate(root)

    # This legacy inspector enforces the NON-FILING serviceId, sender, payload,
    # ds:Reference to Body, and the expected GOST algorithm URIs. It compares
    # an embedded public cert to the input public cert; here that comparison is
    # deliberately NOT interpreted as proof of registry matching.
    result = inspect(embedded, raw)
    if result["sample_type"] != "test-server-bip-demo":
        raise InvalidSoap("Only TEST-server-generated synthetic SOAP is accepted.")

    # The diagnostic endpoint must never become a generic signed-XML upload.
    # Accept only the exact inert server-generated body shape.
    header = root.find(q(SOAP, "Header"))
    if header is None or len(header) != 1 or header[0].tag != q(WSSE, "Security"):
        raise InvalidSoap("Unexpected SOAP Header content.")
    if len(header[0]) != 1 or header[0][0].tag != q(DS, "Signature"):
        raise InvalidSoap("Unexpected WS-Security content.")
    operation = root.find(q(SOAP, "Body"))
    operation = operation.find(q(BIP, "SendMessage")) if operation is not None else None
    data = operation.find("request/requestData/data") if operation is not None else None
    demo = data.find(q(DEMO, "NikaWsSecurityTest")) if data is not None else None
    if demo is None or len(demo) != 2 or demo.attrib:
        raise InvalidSoap("Offline demo XML shape is not permitted.")
    purpose = demo.find(q(DEMO, "Purpose"))
    submission = demo.find(q(DEMO, "Submission"))
    if (
        purpose is None or submission is None
        or (purpose.text or "").strip() != "Server-to-Android offline signature test only"
        or (submission.text or "").strip() != "false"
    ):
        raise InvalidSoap("Only the synthetic TEST purpose is allowed.")

    match = None
    if registered_public_cert is not None:
        if len(registered_public_cert) > 64 * 1024:
            raise InvalidSoap("Registered public certificate exceeds size limit.")
        match = decode_cert(registered_public_cert) == embedded

    fingerprint = hashlib.sha256(embedded).hexdigest().upper()
    # Supports pinning without copying even a public .cer to the TEST VPS.
    # The administrator sets this hash from the already-compared public cert.
    pinned = (os.getenv("ISNA_BIP_REGISTERED_CERT_SHA256") or "").strip().replace(":", "").upper()
    if pinned:
        if not re.fullmatch(r"[A-F0-9]{64}", pinned):
            raise InvalidSoap("Configured public certificate SHA-256 is invalid.")
        pinned_match = fingerprint == pinned
        match = pinned_match if match is None else (match and pinned_match)

    cryptographic = verify_soap_signature_on_vps(soap_xml, embedded)
    return {
        "structureOk": True,
        "sampleType": result["sample_type"],
        "registeredCertMatch": match,
        "embeddedCertSha256": fingerprint,
        "certificateProfile": cert_profile,
        **cryptographic,
        "soapSent": False,
        "filingCreated": False,
        "offlineOnly": True,
    }
