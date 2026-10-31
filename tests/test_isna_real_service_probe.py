"""No-network tests for the real service name, but INVALID tax FNO routing probe."""
import base64
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

from scripts.isna_inspect_wss import (
    SOAP, BIP, WSSE, WSU, DS, EXC_C14N, GOST_SIGNATURE, GOST_DIGEST,
    WSSE_BASE64_BINARY, WSSE_X509V3, InvalidSoap, q,
)
from services import isna_real_service_probe as probe
from services.isna_shep_transport_test import TestGatewayError

FAKE_CERT = b"\x30\x82\x00\x02\x00\x00"


def make_structurally_signed():
    draft = probe.draft_real_service_probe()
    root = ET.fromstring(draft["soapXml"])
    header = root.find(q(SOAP, "Header"))
    body = root.find(q(SOAP, "Body"))
    security = ET.SubElement(header, q(WSSE, "Security"))
    signature = ET.SubElement(security, q(DS, "Signature"))
    info = ET.SubElement(signature, q(DS, "SignedInfo"))
    ET.SubElement(info, q(DS, "CanonicalizationMethod"), Algorithm=EXC_C14N)
    ET.SubElement(info, q(DS, "SignatureMethod"), Algorithm=GOST_SIGNATURE)
    ref = ET.SubElement(info, q(DS, "Reference"), URI="#" + body.get(q(WSU, "Id")))
    transforms = ET.SubElement(ref, q(DS, "Transforms"))
    ET.SubElement(transforms, q(DS, "Transform"), Algorithm=EXC_C14N)
    ET.SubElement(ref, q(DS, "DigestMethod"), Algorithm=GOST_DIGEST)
    ET.SubElement(ref, q(DS, "DigestValue")).text = "TEST_DIGEST_ONLY"
    ET.SubElement(signature, q(DS, "SignatureValue")).text = "TEST_SIGNATURE_ONLY"
    key_info = ET.SubElement(signature, q(DS, "KeyInfo"))
    token = ET.SubElement(key_info, q(WSSE, "SecurityTokenReference"))
    ET.SubElement(
        token, q(WSSE, "KeyIdentifier"),
        EncodingType=WSSE_BASE64_BINARY, ValueType=WSSE_X509V3,
    ).text = base64.b64encode(FAKE_CERT).decode()
    return ET.tostring(root, encoding="unicode")


class RealServiceRoutingTests(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.dict(os.environ, {
            "APP_MODE": "test",
            "ISNA_BIP_URL": "http://195.12.113.7/bip-sync-wss-gost/",
            "ISNA_BIP_SENDER_ID": "nika-registered-test",
            "ISNA_BIP_ROUTING_PROBE_ENABLED": "1",
            "ISNA_BIP_PASSWORD": "DO-NOT-TRANSMIT",
        })
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_draft_uses_real_service_and_sender_but_no_password_or_tax_fields(self):
        draft = probe.draft_real_service_probe()
        self.assertEqual(draft["serviceId"], "FNO_INTEGRATION")
        self.assertTrue(draft["nonFiling"])
        self.assertIn("nika-registered-test", draft["soapXml"])
        self.assertIn("&lt;root/&gt;", draft["soapXml"])
        self.assertNotIn("DO-NOT-TRANSMIT", draft["soapXml"])
        self.assertNotIn("Signature", draft["soapXml"])

    def test_strict_signed_routing_structure(self):
        signed = make_structurally_signed()
        checked = probe.validate_real_service_probe(signed)
        self.assertTrue(checked["structureOk"])
        self.assertEqual(checked["serviceId"], "FNO_INTEGRATION")
        self.assertEqual(checked["certificateProfile"], "key-identifier")
        self.assertFalse(checked["cryptoVerifiedOnServer"])
        self.assertTrue(checked["nonFiling"])

    def test_any_tax_payload_or_real_signed_fno_is_blocked(self):
        soap = make_structurally_signed()
        for edited in (
            soap.replace("&lt;root/&gt;", "&lt;root&gt;&lt;data/&gt;&lt;/root&gt;"),
            soap.replace("FNO_INTEGRATION", "FNO_INTEGRATION_STATUS"),
            soap.replace("nika-registered-test", "another-sender"),
            soap.replace("root/&gt;", "root&gt;ABC&lt;/root&gt;"),
            soap.replace(WSSE_X509V3, "urn:unknown:certificate"),
            soap.replace("KeyIdentifier", "X509Certificate"),
            soap.replace("TEST_DIGEST_ONLY", ""),
            soap.replace("</sender>", "<password>x</password></sender>"),
        ):
            with self.subTest(edited=edited[-180:]):
                with self.assertRaises(InvalidSoap):
                    probe.validate_real_service_probe(edited)

    def test_expired_timestamp_is_blocked(self):
        soap = make_structurally_signed()
        with self.assertRaises(InvalidSoap):
            probe.validate_real_service_probe(
                soap, now=datetime.now(timezone.utc) + timedelta(minutes=40),
            )

    def test_only_test_mode_and_real_sender_allowed(self):
        with patch.dict(os.environ, {"APP_MODE": "prod"}):
            with self.assertRaises(TestGatewayError):
                probe.draft_real_service_probe()
        with patch.dict(os.environ, {"ISNA_BIP_SENDER_ID": ""}):
            with self.assertRaises(TestGatewayError):
                probe.draft_real_service_probe()
        with patch.dict(os.environ, {"ISNA_BIP_SENDER_ID": "smartbridge"}):
            with self.assertRaises(TestGatewayError):
                probe.draft_real_service_probe()
        with patch.dict(os.environ, {"ISNA_BIP_ROUTING_PROBE_ENABLED": "0"}):
            with self.assertRaises(TestGatewayError):
                probe.draft_real_service_probe()

    @patch.object(probe, "local_source_available", return_value=True)
    @patch.object(probe.http.client, "HTTPConnection")
    def test_one_test_ipsec_post_and_never_business_acceptance(self, connection, source):
        response = MagicMock(status=500)
        response.read.return_value = (
            b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            b'<soap:Body><soap:Fault><faultcode>Client</faultcode>'
            b'<faultstring>Invalid business data</faultstring></soap:Fault>'
            b'</soap:Body></soap:Envelope>'
        )
        connection.return_value.getresponse.return_value = response
        soap = make_structurally_signed()
        result = probe.send_real_service_probe(soap)
        self.assertTrue(result["gatewayContacted"])
        self.assertEqual(result["serviceId"], "FNO_INTEGRATION")
        self.assertIsNone(result["businessAccepted"])
        self.assertFalse(result["signedFnoSubmitted"])
        self.assertFalse(result["taxpayerDataSent"])
        connection.assert_called_once_with(
            "195.12.113.7", 80, timeout=12,
            source_address=("195.49.215.49", 0),
        )
        args, kwargs = connection.return_value.request.call_args
        self.assertEqual(args[:2], ("POST", "/bip-sync-wss-gost/"))
        self.assertEqual(kwargs["body"], soap.encode())
        self.assertEqual(kwargs["headers"]["SOAPAction"], '""')

    @patch.object(probe.http.client, "HTTPConnection")
    def test_no_ipsec_means_no_post(self, connection):
        with patch.object(probe, "local_source_available", return_value=False):
            with self.assertRaises(TestGatewayError):
                probe.send_real_service_probe(make_structurally_signed())
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
