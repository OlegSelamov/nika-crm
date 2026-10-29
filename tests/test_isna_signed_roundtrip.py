"""No-network tests for TEST-only Android -> VPS signed SOAP roundtrip."""
import base64
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from scripts.isna_inspect_wss import (
    DS, EXC_C14N, GOST_DIGEST, GOST_SIGNATURE, InvalidSoap, SOAP, WSSE, q,
)
from services import isna_bip
from services.isna_signed_roundtrip import validate_offline_signed_soap
from services.isna_signing_lab import create_server_signing_sample

FAKE_DER = b"\x30\x82\x00\x02\x00\x00"  # synthetic bytes only; NEVER a real cert/signature


def structurally_signed_sample():
    root = ET.fromstring(create_server_signing_sample()["soapXml"])
    header = root.find(q(SOAP, "Header"))
    body = root.find(q(SOAP, "Body"))
    sec = ET.SubElement(header, q(WSSE, "Security"))
    sig = ET.SubElement(sec, q(DS, "Signature"))
    info = ET.SubElement(sig, q(DS, "SignedInfo"))
    ET.SubElement(info, q(DS, "CanonicalizationMethod"), Algorithm=EXC_C14N)
    ET.SubElement(info, q(DS, "SignatureMethod"), Algorithm=GOST_SIGNATURE)
    ref = ET.SubElement(info, q(DS, "Reference"), URI="#" + body.get(
        "{http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd}Id"))
    transforms = ET.SubElement(ref, q(DS, "Transforms"))
    ET.SubElement(transforms, q(DS, "Transform"), Algorithm=EXC_C14N)
    ET.SubElement(ref, q(DS, "DigestMethod"), Algorithm=GOST_DIGEST)
    ET.SubElement(ref, q(DS, "DigestValue")).text = "synthetic"
    ET.SubElement(sig, q(DS, "SignatureValue")).text = "synthetic"
    key_info = ET.SubElement(sig, q(DS, "KeyInfo"))
    x509_data = ET.SubElement(key_info, q(DS, "X509Data"))
    ET.SubElement(x509_data, q(DS, "X509Certificate")).text = base64.b64encode(
        FAKE_DER).decode("ascii")
    return ET.tostring(root, encoding="unicode")


class RoundTripOfflineTests(unittest.TestCase):
    def test_structure_only_and_no_network(self):
        sample = structurally_signed_sample()
        with patch.object(isna_bip.requests, "post") as post:
            result = validate_offline_signed_soap(sample)
            post.assert_not_called()
        self.assertTrue(result["structureOk"])
        self.assertEqual(result["sampleType"], "test-server-bip-demo")
        self.assertIsNone(result["registeredCertMatch"])
        self.assertFalse(result["cryptoVerifiedOnServer"])
        self.assertFalse(result["soapSent"])
        self.assertFalse(result["filingCreated"])

    def test_public_certificate_match_is_optional_and_explicit(self):
        soap = structurally_signed_sample()
        self.assertTrue(validate_offline_signed_soap(
            soap, registered_public_cert=FAKE_DER)["registeredCertMatch"])
        self.assertFalse(validate_offline_signed_soap(
            soap, registered_public_cert=b"\x30\x82\x00\x02\x00\x01")["registeredCertMatch"])

    def test_real_service_id_never_accepted(self):
        soap = structurally_signed_sample().replace(
            "NIKA_ISNA_OFFLINE_SIGNING_ONLY", "FNO_INTEGRATION")
        with self.assertRaises(InvalidSoap):
            validate_offline_signed_soap(soap)

    def test_gateway_password_never_accepted(self):
        soap = structurally_signed_sample().replace(
            "</sender>", "<password>secret</password></sender>")
        with self.assertRaises(InvalidSoap):
            validate_offline_signed_soap(soap)

    def test_unsigned_or_unexpected_payload_refused(self):
        for soap in (
            create_server_signing_sample()["soapXml"],
            structurally_signed_sample().replace(
                "test-server-bip-demo", "something-else"
            ).replace("false</", "true</"),
            '<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a/>',
            "x" * 256001,
        ):
            with self.subTest(length=len(soap)):
                with self.assertRaises(InvalidSoap):
                    validate_offline_signed_soap(soap)

if __name__ == "__main__":
    unittest.main()
