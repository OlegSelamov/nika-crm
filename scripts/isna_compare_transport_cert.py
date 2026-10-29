#!/usr/bin/env python3
"""Offline-only certificate comparison for Smart Bridge transport setup.

Compare the X.509 public certificate downloaded from Smart Bridge (.cer/.crt)
with ds:X509Certificate embedded in the *locally* Kalkan-signed demonstration
XML from Android. Uses only the Python standard library. NEVER opens a .p12,
takes a password, contacts a server, or verifies the XML signature itself.

Usage:
  python scripts/isna_compare_transport_cert.py registered.cer signed-demo.xml
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

DS_NS = "http://www.w3.org/2000/09/xmldsig#"
MAX_CERT_BYTES = 64 * 1024
MAX_XML_BYTES = 4 * 1024 * 1024
BASE64_CERT = re.compile(rb"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----", re.S)


class InvalidCertificateInput(ValueError):
    pass


def _bounded_file(path: Path, max_bytes: int) -> bytes:
    if path.suffix.lower() in {".p12", ".pfx", ".key", ".pem.key"}:
        raise InvalidCertificateInput("Private key files are not accepted. Use only .cer and signed .xml.")
    try:
        if path.stat().st_size > max_bytes:
            raise InvalidCertificateInput("File exceeds the offline test size limit.")
        return path.read_bytes()
    except OSError as exc:
        raise InvalidCertificateInput("Cannot read input file.") from exc


def _decode_certificate_blob(blob: bytes) -> bytes:
    """Return DER encoded public certificate from DER, PEM, or base64 .cer."""
    match = BASE64_CERT.search(blob)
    if match:
        encoded = re.sub(rb"\s+", b"", match.group(1))
    elif blob.startswith(b"0") and any(b > 127 for b in blob[:32]):
        # Binary X.509 DER is a top-level ASN.1 SEQUENCE (0x30).
        return blob
    else:
        # Some exports use bare base64 without PEM delimiters.
        encoded = re.sub(rb"\s+", b"", blob)
    try:
        der = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise InvalidCertificateInput("Not a readable X.509 .cer certificate.") from exc
    if not der.startswith(b"0") or len(der) < 64:
        raise InvalidCertificateInput("Certificate is not DER-encoded X.509.")
    return der


def _extract_xml_certificates(xml_bytes: bytes) -> list[bytes]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise InvalidCertificateInput("Signed XML is not well-formed.") from exc
    signatures = root.findall(".//{%s}Signature" % DS_NS)
    if root.tag == "{%s}Signature" % DS_NS:
        signatures.insert(0, root)
    if not signatures:
        raise InvalidCertificateInput("No ds:Signature was found in XML.")
    candidates = root.findall(".//{%s}X509Certificate" % DS_NS)
    if root.tag == "{%s}X509Certificate" % DS_NS:
        candidates.insert(0, root)
    certificates = []
    for node in candidates:
        encoded = re.sub(r"\s+", "", node.text or "")
        if not encoded:
            continue
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise InvalidCertificateInput("Invalid embedded X509Certificate.") from exc
        if not data.startswith(b"0"):
            raise InvalidCertificateInput("Invalid X.509 certificate in signature.")
        certificates.append(data)
    if not certificates:
        raise InvalidCertificateInput("Signed XML has no embedded ds:X509Certificate.")
    return certificates


def compare_certificates(cer_bytes: bytes, xml_bytes: bytes) -> tuple[bool, str, list[str]]:
    expected = _decode_certificate_blob(cer_bytes)
    embedded = _extract_xml_certificates(xml_bytes)
    return (
        expected in embedded,
        hashlib.sha256(expected).hexdigest().upper(),
        [hashlib.sha256(value).hexdigest().upper() for value in embedded],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Smart Bridge CER / signed XML match")
    parser.add_argument("cer", type=Path, help="Public .cer/.crt uploaded to Smart Bridge")
    parser.add_argument("signed_xml", type=Path, help="Android signed demonstration .xml")
    args = parser.parse_args(argv)
    if args.cer.suffix.lower() not in {".cer", ".crt", ".pem", ".der"}:
        parser.error("Only a public certificate (.cer/.crt/.pem/.der) is accepted as the first file.")
    if args.signed_xml.suffix.lower() != ".xml":
        parser.error("The second file must be the signed .xml, NOT a .p12.")
    try:
        match, expected_fingerprint, embedded_fingerprints = compare_certificates(
            _bounded_file(args.cer, MAX_CERT_BYTES),
            _bounded_file(args.signed_xml, MAX_XML_BYTES),
        )
    except InvalidCertificateInput as exc:
        print("RESULT: ERROR - " + str(exc), file=sys.stderr)
        print("NO NETWORK, NO SOAP, NO PRIVATE KEY USED.")
        return 2

    print("REGISTERED_CER_SHA256: " + expected_fingerprint)
    for index, fingerprint in enumerate(embedded_fingerprints, start=1):
        print("XML_CERT_SHA256_%d: %s" % (index, fingerprint))
    print("CERT_MATCH: " + ("YES" if match else "NO"))
    print("This only compares PUBLIC certificates; cryptographic XML signature")
    print("verification, private key possession, and WS-Security are NOT checked.")
    print("NO NETWORK, NO SOAP, NO PRIVATE KEY USED.")
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
