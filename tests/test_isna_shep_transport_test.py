"""Deterministic no-network tests for the TEST-only WShEP SOAP POST."""
import os
import unittest
from unittest.mock import MagicMock, patch
import base64
from xml.etree import ElementTree as ET

from services import isna_shep_transport_test as gate
from services.isna_signing_lab import create_server_signing_sample
from scripts.isna_inspect_wss import SOAP, WSSE, DS, EXC_C14N, GOST_DIGEST, GOST_SIGNATURE, WSU, q

FAKE_PUBLIC_DER = b"\x30\x82\x00\x02\x00\x00"


def demo_signed():
    root = ET.fromstring(create_server_signing_sample()["soapXml"])
    header = root.find(q(SOAP, "Header"))
    body = root.find(q(SOAP, "Body"))
    sec = ET.SubElement(header, q(WSSE, "Security"))
    signature = ET.SubElement(sec, q(DS, "Signature"))
    si = ET.SubElement(signature, q(DS, "SignedInfo"))
    ET.SubElement(si, q(DS, "CanonicalizationMethod"), Algorithm=EXC_C14N)
    ET.SubElement(si, q(DS, "SignatureMethod"), Algorithm=GOST_SIGNATURE)
    ref = ET.SubElement(si, q(DS, "Reference"), URI="#" + body.get(q(WSU, "Id")))
    transforms = ET.SubElement(ref, q(DS, "Transforms"))
    ET.SubElement(transforms, q(DS, "Transform"), Algorithm=EXC_C14N)
    ET.SubElement(ref, q(DS, "DigestMethod"), Algorithm=GOST_DIGEST)
    ET.SubElement(ref, q(DS, "DigestValue")).text = "FAKE_TEST_DIGEST"
    ET.SubElement(signature, q(DS, "SignatureValue")).text = "FAKE_TEST_SIGNATURE"
    key = ET.SubElement(signature, q(DS, "KeyInfo"))
    info = ET.SubElement(key, q(DS, "X509Data"))
    ET.SubElement(info, q(DS, "X509Certificate")).text = base64.b64encode(
        FAKE_PUBLIC_DER).decode()
    return ET.tostring(root, encoding="unicode")


class TestTransport(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "APP_MODE": "test", "ISNA_BIP_TEST_POST_ENABLED": "1",
            "ISNA_BIP_URL": "http://195.12.113.7/bip-sync-wss-gost/",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    @patch.object(gate, "local_source_available", return_value=True)
    @patch.object(gate.http.client, "HTTPConnection")
    def test_exactly_one_pinned_ipsec_post_and_soap_fault(self, connection, source):
        response = MagicMock(status=500)
        response.read.return_value = (
            b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            b'<soap:Body><soap:Fault><faultcode>Client</faultcode>'
            b'<faultstring>Unknown serviceId</faultstring></soap:Fault>'
            b'</soap:Body></soap:Envelope>'
        )
        connection.return_value.getresponse.return_value = response
        sample = demo_signed()
        result = gate.send_synthetic_signed_soap(sample)
        self.assertTrue(result["gatewayContacted"])
        self.assertEqual(result["httpStatus"], 500)
        self.assertEqual(result["responseType"], "soap-fault")
        self.assertEqual(result["faultMessage"], "Unknown serviceId")
        self.assertFalse(result["filingCreated"])
        connection.assert_called_once_with(
            "195.12.113.7", 80,
            timeout=12, source_address=("195.49.215.49", 0),
        )
        args, kwargs = connection.return_value.request.call_args
        self.assertEqual(args[:2], ("POST", "/bip-sync-wss-gost/"))
        self.assertEqual(kwargs["body"], sample.encode())
        self.assertEqual(kwargs["headers"]["SOAPAction"], '""')
        self.assertNotIn("FNO_INTEGRATION", sample)

    @patch.object(gate.http.client, "HTTPConnection")
    def test_never_posts_actual_fno_or_arbitrary_data(self, connection):
        with patch.object(gate, "local_source_available", return_value=True):
            with self.assertRaises(gate.TestGatewayError):
                gate.send_synthetic_signed_soap(
                    demo_signed().replace("NIKA_ISNA_OFFLINE_SIGNING_ONLY", "FNO_INTEGRATION"),
                )
            with self.assertRaises(gate.TestGatewayError):
                gate.send_synthetic_signed_soap(demo_signed().replace(
                    "nika-offline-test", "registered-real-sender"),
                )
            with self.assertRaises(gate.TestGatewayError):
                gate.send_synthetic_signed_soap("<root/>")
        connection.assert_not_called()

    @patch.object(gate.http.client, "HTTPConnection")
    def test_no_ipsec_source_no_post(self, connection):
        with patch.object(gate, "local_source_available", return_value=False):
            with self.assertRaises(gate.TestGatewayError):
                gate.send_synthetic_signed_soap(demo_signed())
        connection.assert_not_called()

    @patch.object(gate.http.client, "HTTPConnection")
    def test_production_always_rejected(self, connection):
        with patch.dict(os.environ, {"APP_MODE": "prod"}):
            with self.assertRaises(gate.TestGatewayError):
                gate.send_synthetic_signed_soap(demo_signed())
        connection.assert_not_called()

    @patch.object(gate.http.client, "HTTPConnection")
    def test_public_cert_mismatch_blocks_post(self, connection):
        with patch.object(gate, "local_source_available", return_value=True):
            with self.assertRaises(gate.TestGatewayError):
                gate.send_synthetic_signed_soap(
                    demo_signed(), registered_public_cert=b"\x30\x82\x00\x02\x00\x09",
                )
        connection.assert_not_called()

    @patch.object(gate.http.client, "HTTPConnection")
    def test_config_disabled_blocks_post(self, connection):
        with patch.dict(os.environ, {"ISNA_BIP_TEST_POST_ENABLED": "0"}):
            with self.assertRaises(gate.TestGatewayError):
                gate.send_synthetic_signed_soap(demo_signed())
        connection.assert_not_called()

if __name__ == "__main__":
    unittest.main()
