"""No-network regression tests for the official FNO_INTEGRATION wire format."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from services import isna_bip
from services import isna_fno_integration as fno


def example_signed_fno(code="200.00"):
    body = json.dumps({"code": code, "fnoDto": {"taxpayerType": "FL"}}, ensure_ascii=False)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<root><data><![CDATA[' + body + ']]></data>'
        '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
        '<ds:SignedInfo><ds:Reference URI=""/></ds:SignedInfo>'
        '<ds:SignatureValue>SYNTHETIC_NOT_A_REAL_SIGNATURE</ds:SignatureValue>'
        '</ds:Signature></root>'
    )


def response(status="OK", service_success=True):
    data = json.dumps({"success": service_success, "fno_id": 42})
    return (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
        ' xmlns:typ="http://bip.bee.kz/SyncChannel/v10/Types">'
        '<soap:Header/><soap:Body><typ:SendMessageResponse><response>'
        '<responseInfo><status><code>' + status + '</code>'
        '<message>sample</message></status></responseInfo>'
        '<responseData><data>' + data + '</data></responseData>'
        '</response></typ:SendMessageResponse></soap:Body></soap:Envelope>'
    )


class FnoOfflineTests(unittest.TestCase):
    def test_valid_signature_shape_is_structural_only(self):
        result = fno.inspect_taxpayer_signed_fno(example_signed_fno())
        self.assertEqual(result["form_code"], "200.00")
        self.assertTrue(result["xml_signature_present"])
        self.assertFalse(result["cryptographic_signature_verified"])

    def test_string_payload_exactly_matches_inner_xml(self):
        inner = example_signed_fno("910.00")
        with patch.object(isna_bip.requests, "post") as post:
            outer = fno.build_fno_integration_soap(
                inner, sender_id="synthetic-system", sender_password="synthetic-password",
            )
            post.assert_not_called()
        root = ET.fromstring(outer)
        data = root.find(".//requestData/data")
        self.assertIsNotNone(data)
        self.assertEqual(data.get("{" + isna_bip.XSI_NS + "}type"), "xs:string")
        self.assertIn("xmlns:xs=", outer)
        self.assertEqual(data.text, inner)
        self.assertEqual(len(data), 0)
        self.assertEqual(root.findtext(".//requestInfo/serviceId"), "FNO_INTEGRATION")
        self.assertEqual(root.findtext(".//sender/senderId"), "synthetic-system")
        self.assertEqual(root.findtext(".//sender/password"), "synthetic-password")

    def test_existing_generic_xml_mode_unchanged(self):
        outer = isna_bip.build_sync_envelope(
            "<Sample/>", sender_id="synthetic-system",
            service_id="example-service",
        )
        self.assertIsNotNone(ET.fromstring(outer).find(".//requestData/data/Sample"))

    def test_reject_unsigned_or_malformed_tax_form(self):
        good = example_signed_fno()
        bad = [
            "<root><data>{}</data></root>",
            good.replace("]]></data>", "]></data>"),
            good.replace('"code": "200.00"', '"code": 200.00'),
            good.replace("<ds:Signature", "<ds:WrongSignature").replace("</ds:Signature>", "</ds:WrongSignature>"),
            "<!DOCTYPE root [<!ENTITY example SYSTEM 'file:///etc/passwd'>]><root/>",
        ]
        for xml in bad:
            with self.subTest(xml=xml[:40]):
                with self.assertRaises(isna_bip.IsnaBipError):
                    fno.inspect_taxpayer_signed_fno(xml)

    def test_refuse_sample_sender_and_missing_sender(self):
        for sender in ("smartbridge", "", "  "):
            with self.subTest(sender=sender):
                with self.assertRaises(isna_bip.IsnaBipError):
                    fno.build_fno_integration_soap(
                        example_signed_fno(), sender_id=sender,
                    )

    def test_response_needs_both_success_codes(self):
        self.assertTrue(fno.parse_fno_integration_response(response())["ok"])
        self.assertEqual(fno.parse_fno_integration_response(response())["fno_id"], 42)
        self.assertFalse(fno.parse_fno_integration_response(response(status="ERROR"))["ok"])
        self.assertFalse(fno.parse_fno_integration_response(response(service_success=False))["ok"])

    def test_soap_fault_does_not_mean_fno_accepted(self):
        soap = (
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            '<s:Body><s:Fault><faultcode>Client</faultcode>'
            '<faultstring>Not authorized</faultstring></s:Fault></s:Body></s:Envelope>'
        )
        parsed = fno.parse_fno_integration_response(soap)
        self.assertFalse(parsed["ok"])
        self.assertTrue(parsed["fault"])
        self.assertIsNone(parsed["fno_id"])

    def test_invalid_response_rejected(self):
        with self.assertRaises(isna_bip.IsnaBipError):
            fno.parse_fno_integration_response("<anything/>")
        with self.assertRaises(isna_bip.IsnaBipError):
            fno.parse_fno_integration_response(response().replace('"success": true', "not-json"))

    def test_no_network_by_accident(self):
        with patch.object(isna_bip.requests, "post") as post:
            _ = fno.inspect_taxpayer_signed_fno(example_signed_fno())
            _ = fno.parse_fno_integration_response(response())
            _ = fno.build_fno_integration_soap(example_signed_fno(), sender_id="synthetic-system")
            post.assert_not_called()




class FnoCliOfflineTests(unittest.TestCase):
    def test_prepare_unsigned_uses_string_mode_and_creates_private_file(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "synthetic-fno.xml"
            output = directory / "soap-draft.xml"
            source.write_text(example_signed_fno(), encoding="utf-8")
            env = {
                "APP_MODE": "test",
                "ISNA_BIP_SENDER_ID": "synthetic-system",
                "ISNA_BIP_SERVICE_ID": "FNO_INTEGRATION",
                "ISNA_BIP_PASSWORD": "",
            }
            argv = [
                "services.isna_bip", "--prepare-unsigned", str(source),
                "--output", str(output),
            ]
            with patch.dict(os.environ, env), patch.object(sys, "argv", argv), \
                 patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                 patch.object(isna_bip.requests, "post") as post:
                self.assertEqual(isna_bip._main(), 0)
                post.assert_not_called()
                self.assertIn("NOT SENT", stdout.getvalue())
            outer = ET.parse(output).getroot()
            body_data = outer.find(".//requestData/data")
            self.assertEqual(body_data.get("{" + isna_bip.XSI_NS + "}type"), "xs:string")
            self.assertEqual(body_data.text, example_signed_fno())
            if os.name == "posix":
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)

if __name__ == "__main__":
    unittest.main()
