#!/usr/bin/env python3
"""Read-only offline structural check for Nika's SOAP WS-Security GOST demo.

It does NOT verify a digital signature cryptographically (Kalkan Android does
that independently), does NOT read .p12, does NOT send SOAP and does NOT access
the network. Accepts only a public registered .cer/.crt plus the saved offline
SOAP XML. Intentionally checks that the payload is the inert Nika demo.
"""
import argparse
import base64
import binascii
import hashlib
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
DS = "http://www.w3.org/2000/09/xmldsig#"
DEMO = "urn:nikabusiness:offline-soap-test:1"
GOST_SIGNATURE = "urn:ietf:params:xml:ns:pkigovkz:xmlsec:algorithms:gostr34102015-gostr34112015-512"
GOST_DIGEST = "urn:ietf:params:xml:ns:pkigovkz:xmlsec:algorithms:gostr34112015-512"
EXC_C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
CERT_LIMIT = 64 * 1024
XML_LIMIT = 4 * 1024 * 1024


class InvalidSoap(ValueError):
    pass


def q(ns, name):
    return "{%s}%s" % (ns, name)


def decode_cert(source):
    match = re.search(rb"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----", source, re.S)
    if match:
        source = match.group(1)
    elif source.startswith(b"\x30") and any(v > 127 for v in source[:32]):
        return source
    try:
        raw = base64.b64decode(re.sub(rb"\s+", b"", source), validate=True)
    except (binascii.Error, ValueError) as e:
        raise InvalidSoap("Registered .cer is not readable PEM/DER/base64.") from e
    if not raw.startswith(b"\x30"):
        raise InvalidSoap("Registered .cer is not an X.509 DER certificate.")
    return raw


def inspect(registered_cer, soap_xml):
    try:
        root = ET.fromstring(soap_xml)
    except ET.ParseError as e:
        raise InvalidSoap("Signed SOAP XML is not well-formed.") from e
    if root.tag != q(SOAP, "Envelope"):
        raise InvalidSoap("Expected SOAP 1.1 Envelope.")
    headers = root.findall(q(SOAP, "Header"))
    bodies = root.findall(q(SOAP, "Body"))
    if len(headers) != 1 or len(bodies) != 1:
        raise InvalidSoap("Expected exactly one SOAP Header and Body.")
    header, body = headers[0], bodies[0]
    body_id = body.get(q(WSU, "Id"))
    if not body_id or not re.fullmatch(r"id-[A-Za-z0-9-]{8,96}", body_id):
        raise InvalidSoap("SOAP Body has no valid wsu:Id.")

    demos = body.findall(q(DEMO, "NikaWsSecurityTest"))
    if len(list(body)) != 1 or len(demos) != 1:
        raise InvalidSoap("Only the inert local Nika SOAP demo is allowed.")
    submission = demos[0].find(q(DEMO, "Submission"))
    if submission is None or (submission.text or "").strip() != "false":
        raise InvalidSoap("Offline demo must contain Submission=false.")

    sec = header.findall(q(WSSE, "Security"))
    if len(sec) != 1:
        raise InvalidSoap("Expected wsse:Security in SOAP Header.")
    sig = sec[0].find(q(DS, "Signature"))
    if sig is None:
        raise InvalidSoap("Missing ds:Signature in wsse:Security.")
    if len(root.findall(".//" + q(DS, "Signature"))) != 1:
        raise InvalidSoap("Expected exactly one XMLDSig Signature.")
    info = sig.find(q(DS, "SignedInfo"))
    if info is None:
        raise InvalidSoap("Missing ds:SignedInfo.")
    references = info.findall(q(DS, "Reference"))
    if len(references) != 1 or references[0].get("URI") != "#" + body_id:
        raise InvalidSoap("ds:Reference does not point to SOAP Body wsu:Id.")
    method = info.find(q(DS, "SignatureMethod"))
    digest = references[0].find(q(DS, "DigestMethod"))
    canonicalization = info.find(q(DS, "CanonicalizationMethod"))
    if method is None or method.get("Algorithm") != GOST_SIGNATURE:
        raise InvalidSoap("Expected GOST 2015-512 XML signature algorithm.")
    if digest is None or digest.get("Algorithm") != GOST_DIGEST:
        raise InvalidSoap("Expected GOST 2015-512 digest.")
    if canonicalization is None or canonicalization.get("Algorithm") != EXC_C14N:
        raise InvalidSoap("Expected exclusive XML canonicalization.")
    transforms = references[0].find(q(DS, "Transforms"))
    if transforms is None or [x.get("Algorithm") for x in transforms.findall(q(DS, "Transform"))] != [EXC_C14N]:
        raise InvalidSoap("Body reference must use exclusive C14N transform.")
    value = sig.find(q(DS, "SignatureValue"))
    if value is None or not (value.text or "").strip():
        raise InvalidSoap("Signed XML has no ds:SignatureValue.")
    cert = sig.find(".//" + q(DS, "X509Certificate"))
    if cert is None or not (cert.text or "").strip():
        raise InvalidSoap("Missing embedded public X.509 certificate.")
    try:
        embedded = base64.b64decode(re.sub(r"\s+", "", cert.text), validate=True)
    except (binascii.Error, ValueError) as e:
        raise InvalidSoap("Invalid base64 embedded X.509 certificate.") from e

    public = decode_cert(registered_cer)
    return {
        "structure_ok": True,
        "cert_match": public == embedded,
        "fingerprint": hashlib.sha256(public).hexdigest().upper(),
    }


def bounded_file(path, limit):
    if path.suffix.lower() in (".p12", ".pfx", ".key"):
        raise InvalidSoap("Do not provide a private key file.")
    try:
        if path.stat().st_size > limit:
            raise InvalidSoap("Input exceeds safety size limit.")
        return path.read_bytes()
    except OSError as e:
        raise InvalidSoap("Could not read the provided public .cer or signed .xml.") from e


def main():
    parser = argparse.ArgumentParser(description="Offline Nika SOAP WS-Security structural check")
    parser.add_argument("cer", type=Path, help="Public .cer uploaded to Smart Bridge")
    parser.add_argument("soap", type=Path, help="Saved offline SOAP XML from Android TEST")
    args = parser.parse_args()
    if args.cer.suffix.lower() not in (".cer", ".crt", ".pem", ".der"):
        parser.error("The first file must be a PUBLIC .cer/.crt/.pem/.der.")
    if args.soap.suffix.lower() != ".xml":
        parser.error("The second file must be the offline signed .xml.")
    try:
        result = inspect(bounded_file(args.cer, CERT_LIMIT), bounded_file(args.soap, XML_LIMIT))
    except InvalidSoap as error:
        print("SOAP_STRUCTURE: ERROR - " + str(error))
        print("NO NETWORK, NO SOAP SUBMITTED, NO PRIVATE KEY USED.")
        return 2
    print("SOAP_STRUCTURE: OK")
    print("REGISTERED_CERT_MATCH: " + ("YES" if result["cert_match"] else "NO"))
    print("CERT_SHA256: " + result["fingerprint"])
    print("CRYPTO_SIGNATURE_VERIFICATION: NOT PERFORMED HERE (Kalkan Android only)")
    print("NO NETWORK, NO SOAP SUBMITTED, NO PRIVATE KEY USED.")
    return 0 if result["cert_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
