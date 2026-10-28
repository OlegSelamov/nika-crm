"""Offline tests for the Smart Bridge SyncChannel v10 XML wrapper.

These tests NEVER send tax filings or use a real transport key.
Run: python -m unittest discover -s tests -p 'test_isna_bip.py' -v
"""
import os
import unittest
from unittest.mock import patch, Mock
from xml.etree import ElementTree as ET

from services import isna_bip as bip


class IsnaBipEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "APP_MODE": "test",
            "ISNA_BIP_SENDER_ID": "fake-test-sender",
            "ISNA_BIP_PASSWORD": "fake-test-password",
            "ISNA_BIP_SERVICE_ID": "fake-test-service",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def _elements(self):
        xml = bip.build_sync_envelope('<demo xmlns="urn:nika:offline-test"><value>ok</value></demo>')
        root = ET.fromstring(xml)
        body = root.find(f'{{{bip.SOAP_NS}}}Body')
        self.assertIsNotNone(body)
        operation = body.find(f'{{{bip.BIP_TYPES_NS}}}SendMessage')
        self.assertIsNotNone(operation)
        request = operation.find('request')
        self.assertIsNotNone(request)
        return root, request

    def test_matches_wsdl_structure_and_required_request_data_wrapper(self):
        _, request = self._elements()
        info = request.find("requestInfo")
        self.assertIsNotNone(info)
        self.assertTrue(info.findtext("messageId"))
        self.assertEqual(info.findtext("serviceId"), "fake-test-service")
        self.assertTrue(info.findtext("messageDate"))
        self.assertEqual(info.findtext("sender/senderId"), "fake-test-sender")
        self.assertEqual(info.findtext("sender/password"), "fake-test-password")
        self.assertIsNone(info.find("sessionId"), "BIP assigns sessionId; client should omit by default")
        data = request.find("requestData/data")
        self.assertIsNotNone(data, "WSDL requires requestData/data (not direct payload)")
        payload = data.find("{urn:nika:offline-test}demo")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.findtext("{urn:nika:offline-test}value"), "ok")

    def test_explicit_session_id_only_when_supplied(self):
        xml = bip.build_sync_envelope('<test />', session_id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}")
        root = ET.fromstring(xml)
        self.assertIsNotNone(root.find(".//sessionId"))

    def test_password_optional_under_wsdl(self):
        xml = bip.build_sync_envelope("<test/>", sender_password="")
        root = ET.fromstring(xml)
        self.assertIsNone(root.find(".//password"))

    def test_bad_payload_rejected_without_network(self):
        with self.assertRaises(bip.IsnaBipError):
            bip.build_sync_envelope("<not-closed")

    def test_default_soap_action_matches_wsdl(self):
        with patch.dict(os.environ, {"ISNA_BIP_SOAP_ACTION": ""}):
            self.assertEqual(bip.configuration().soap_action, "")

    def test_post_is_not_called_without_explicit_invocation(self):
        with patch.object(bip.requests, "post") as post:
            self._elements()
            post.assert_not_called()

    def test_signed_post_soapaction_header_from_wsdl(self):
        response = Mock()
        with patch.object(bip.requests, "post", return_value=response) as post:
            bip.post_signed_envelope("<signed-test/>")
        self.assertEqual(post.call_args.kwargs["headers"]["SOAPAction"], '""')


if __name__ == "__main__":
    unittest.main()
