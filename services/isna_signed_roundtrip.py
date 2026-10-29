"""Offline-only Android -> TEST VPS SOAP diagnostic (never sends to SHÈP).

Accepts ONLY the synthetic Nika server signing sample, which deliberately
uses an invalid serviceId. This module DOES NOT verify GOST cryptography:
that check is performed locally by Android/KalkanCrypt before upload.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
import xml.etree.ElementTree as ET

from scripts.isna_inspect_wss import (
    DS, InvalidSoap, decode_cert, inspect, q,
)

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

    embedded_nodes = root.findall(".//" + q(DS, "X509Certificate"))
    if len(embedded_nodes) != 1 or not (embedded_nodes[0].text or "").strip():
        raise InvalidSoap("Exactly one public signer certificate is required.")
    try:
        embedded = base64.b64decode(
            re.sub(r"\s+", "", embedded_nodes[0].text), validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise InvalidSoap("Invalid embedded public certificate.") from exc
    if len(embedded) < 3 or len(embedded) > 64 * 1024 or embedded[0] != 0x30:
        raise InvalidSoap("Embedded X.509 public certificate has invalid format.")

    # This legacy inspector enforces the NON-FILING serviceId, sender, payload,
    # ds:Reference to Body, and the expected GOST algorithm URIs. It compares
    # an embedded public cert to the input public cert; here that comparison is
    # deliberately NOT interpreted as proof of registry matching.
    result = inspect(embedded, raw)
    if result["sample_type"] != "test-server-bip-demo":
        raise InvalidSoap("Only TEST-server-generated synthetic SOAP is accepted.")

    match = None
    if registered_public_cert is not None:
        if len(registered_public_cert) > 64 * 1024:
            raise InvalidSoap("Registered public certificate exceeds size limit.")
        match = decode_cert(registered_public_cert) == embedded
    return {
        "structureOk": True,
        "sampleType": result["sample_type"],
        "registeredCertMatch": match,
        "embeddedCertSha256": hashlib.sha256(embedded).hexdigest().upper(),
        "cryptoVerifiedOnServer": False,
        "soapSent": False,
        "filingCreated": False,
        "offlineOnly": True,
    }
