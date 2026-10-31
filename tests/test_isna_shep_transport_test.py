"""Deterministic no-network tests for the TEST-only WShEP SOAP POST."""
import os
import unittest
from unittest.mock import MagicMock, patch
import base64
from xml.etree import ElementTree as ET

from services import isna_shep_transport_test as gate
from services.isna_signing_lab import create_server_signing_sample
from scripts.isna_inspect_wss import (
    SOAP, WSSE, DS, EXC_C14N, GOST_DIGEST, GOST_SIGNATURE, WSU,
    WSSE_BASE64_BINARY, WSSE_X509V3, q,
)

FAKE_PUBLIC_DER = b"\x30\x82\x00\x02\x00\x00"


def demo_signed(*, key_identifier=False):
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
    if key_identifier:
        token_ref = ET.SubElement(key, q(WSSE, "SecurityTokenReference"))
        ET.SubElement(
            token_ref, q(WSSE, "KeyIdentifier"),
            EncodingType=WSSE_BASE64_BINARY, ValueType=WSSE_X509V3,
        ).text = base64.b64encode(FAKE_PUBLIC_DER).decode()
    else:
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

    def test_sce005_extracts_gateway_code_timestamp_and_session(self):
        response = (
            b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            b'<soap:Body><soap:Fault><faultcode>soap:Server</faultcode>'
            b'<faultstring>\\xd0\\xa2\\xd1\\x80\\xd0\\xb0\\xd0\\xbd\\xd1\\x81\\xd0\\xbf\\xd0\\xbe\\xd1\\x80\\xd1\\x82\\xd0\\xbd\\xd0\\xb0\\xd1\\x8f '
            b'\\xd0\\xbf\\xd0\\xbe\\xd0\\xb4\\xd0\\xbf\\xd0\\xb8\\xd1\\x81\\xd1\\x8c '
            b'\\xd0\\xbd\\xd0\\xb5 \\xd0\\xb0\\xd0\\xba\\xd1\\x82\\xd1\\x83\\xd0\\xb0\\xd0\\xbb\\xd1\\x8c\\xd0\\xbd\\xd0\\xb0\\xd1\\x8f</faultstring>'
            b'<detail><x:Fault xmlns:x="http://bip.bee.kz/SyncChannel/v10/Types">'
            b'<errorCode>SCE005</errorCode>'
            b'<errorDate>2026-10-30T01:30:00+05:00</errorDate>'
            b'<sessionId>{1234abcd-0000-4000-8000-123456789abc}</sessionId>'
            b'</x:Fault></detail></soap:Fault></soap:Body></soap:Envelope>'
        )
        parsed = gate._safe_gateway_reply(response, False)
        self.assertEqual(parsed["responseType"], "soap-fault")
        self.assertEqual(parsed["gatewayErrorCode"], "SCE005")
        self.assertEqual(parsed["gatewayErrorDate"], "2026-10-30T01:30:00+05:00")
        self.assertEqual(parsed["gatewaySessionId"], "{1234abcd-0000-4000-8000-123456789abc}")

    @patch.object(gate, "local_source_available", return_value=True)
    @patch.object(gate.http.client, "HTTPConnection")
    def test_key_identifier_profile_can_reach_only_pinned_test_gateway(self, connection, source):
        response = MagicMock(status=500)
        response.read.return_value = (
            b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            b'<soap:Body><soap:Fault><faultcode>soap:Client</faultcode>'
            b'<faultstring>SCE005</faultstring></soap:Fault></soap:Body></soap:Envelope>'
        )
        connection.return_value.getresponse.return_value = response
        soap = demo_signed(key_identifier=True)
        result = gate.send_synthetic_signed_soap(soap)
        self.assertEqual(result["httpStatus"], 500)
        self.assertTrue(result["soapFault"])
        self.assertEqual(result["sampleType"], "test-server-bip-demo")
        args, kwargs = connection.return_value.request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "/bip-sync-wss-gost/")
        self.assertEqual(kwargs["body"], soap.encode("utf-8"))
        self.assertNotIn("FNO_INTEGRATION", soap)

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
