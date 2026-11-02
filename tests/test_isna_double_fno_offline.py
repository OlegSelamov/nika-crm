"""Offline-only double FNO preflight: no private keys or government HTTP."""
import base64
from html import escape
import unittest
from unittest.mock import patch

from scripts.isna_inspect_wss import (
    DS, SOAP, WSSE, WSU, BIP, InvalidSoap,
    GOST_SIGNATURE, GOST_DIGEST, EXC_C14N,
    WSSE_BASE64_BINARY, WSSE_X509V3,
)
from services.isna_double_fno_offline import (
    inspect_offline_double_soap, verify_offline_double_soap,
    XML_C14N_INCLUSIVE, XML_C14N_INCL_COMMENTS, XML_ENVELOPED,
)
from services.isna_vps_signature_verifier import verify_inner_fno_signature_on_vps


class DoubleFnoOfflineTests(unittest.TestCase):
    def make_sample(self):
        cert = base64.b64encode(b"\x30\x82\x01\x01").decode()
        json_payload = '{"code":"000.00","fnoDto":{"nikaOfflineDemo":true}}'
        inner = (
            '<root xmlns:ds="' + DS + '"><data><![CDATA['
            + json_payload +
            ']]></data><ds:Signature><ds:SignedInfo>'
            '<ds:CanonicalizationMethod Algorithm="' + XML_C14N_INCLUSIVE + '"/>'
            '<ds:SignatureMethod Algorithm="' + GOST_SIGNATURE + '"/>'
            '<ds:Reference URI=""><ds:Transforms>'
            '<ds:Transform Algorithm="' + XML_ENVELOPED + '"/>'
            '<ds:Transform Algorithm="' + XML_C14N_INCL_COMMENTS + '"/>'
            '</ds:Transforms><ds:DigestMethod Algorithm="' + GOST_DIGEST + '"/>'
            '<ds:DigestValue>abc</ds:DigestValue></ds:Reference></ds:SignedInfo>'
            '<ds:SignatureValue>abc</ds:SignatureValue><ds:KeyInfo><ds:X509Data>'
            '<ds:X509Certificate>' + cert + '</ds:X509Certificate>'
            '</ds:X509Data></ds:KeyInfo></ds:Signature></root>'
        )
        soap = (
            '<soap:Envelope xmlns:soap="' + SOAP + '" xmlns:ds="' + DS + '"'
            ' xmlns:wsse="' + WSSE + '" xmlns:wsu="' + WSU + '"'
            ' xmlns:typ="' + BIP + '"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<soap:Header><wsse:Security><ds:Signature>'
            '<ds:SignedInfo><ds:CanonicalizationMethod Algorithm="' + EXC_C14N + '"/>'
            '<ds:SignatureMethod Algorithm="' + GOST_SIGNATURE + '"/>'
            '<ds:Reference URI="#id-fno-offline-12345"><ds:Transforms>'
            '<ds:Transform Algorithm="' + EXC_C14N + '"/>'
            '</ds:Transforms><ds:DigestMethod Algorithm="' + GOST_DIGEST + '"/>'
            '<ds:DigestValue>abc</ds:DigestValue></ds:Reference></ds:SignedInfo>'
            '<ds:SignatureValue>abc</ds:SignatureValue><ds:KeyInfo>'
            '<wsse:SecurityTokenReference><wsse:KeyIdentifier '
            'EncodingType="' + WSSE_BASE64_BINARY + '" '
            'ValueType="' + WSSE_X509V3 + '">' + cert +
            '</wsse:KeyIdentifier></wsse:SecurityTokenReference>'
            '</ds:KeyInfo></ds:Signature></wsse:Security></soap:Header>'
            '<soap:Body wsu:Id="id-fno-offline-12345"><typ:SendMessage>'
            '<request><requestInfo><messageId>00000000-0000-4000-8000-000000000001</messageId>'
            '<serviceId>FNO_INTEGRATION</serviceId><messageDate>2026-11-02T00:00:00Z</messageDate>'
            '<sender><senderId>nika-fno-offline-only</senderId></sender></requestInfo>'
            '<requestData><data xmlns:xs="http://www.w3.org/2001/XMLSchema" '
            'xsi:type="xs:string">' + escape(inner) + '</data></requestData>'
            '</request></typ:SendMessage></soap:Body></soap:Envelope>'
        )
        return soap, inner

    def test_fixed_sample_structure_and_inner_text_extracted_verbatim(self):
        soap, inner = self.make_sample()
        extracted, cert = inspect_offline_double_soap(soap)
        self.assertEqual(extracted, inner)
        self.assertEqual(cert, b"\x30\x82\x01\x01")

    def test_rejects_real_sender_form_and_modified_signed_reference(self):
        original, _ = self.make_sample()
        for altered in (
            original.replace("nika-fno-offline-only", "registered-sender"),
            original.replace('000.00', '910.00'),
            original.replace('"#id-fno-offline-12345"', '"#id-wrong"'),
            original.replace("<serviceId>FNO_INTEGRATION</serviceId>",
                             "<serviceId>FNO_INTEGRATION_STATUS</serviceId>"),
            original.replace('xsi:type="xs:string"', 'xsi:type="xs:base64Binary"'),
            original.replace('nikaOfflineDemo', 'taxpayerBin'),
            original.replace("<soap:Envelope", '<!DOCTYPE foo><soap:Envelope', 1),
        ):
            with self.subTest(altered=altered[:80]), self.assertRaises(InvalidSoap):
                inspect_offline_double_soap(altered)

    def test_independent_native_checks_never_fabricate_success(self):
        soap, inner = self.make_sample()
        with patch("services.isna_double_fno_offline.verify_soap_signature_on_vps") as outer, \
             patch("services.isna_double_fno_offline.verify_inner_fno_signature_on_vps") as inner_check:
            outer.return_value = dict(cryptoVerifiedOnServer=True, cryptoVerificationStatus="verified",
                                      cryptoNativeCode="0x00000000")
            inner_check.return_value = dict(cryptoVerifiedOnServer=False, cryptoVerificationStatus="invalid",
                                            cryptoNativeCode="0x08F0001C")
            result = verify_offline_double_soap(soap)
            self.assertFalse(result["bothVerified"])
            self.assertFalse(result["gatewayContacted"])
            self.assertFalse(result["filingCreated"])
            inner_check.assert_called_once_with(inner)
            outer.assert_called_once()

            inner_check.return_value = dict(cryptoVerifiedOnServer=True, cryptoVerificationStatus="verified",
                                            cryptoNativeCode="0x00000000")
            result = verify_offline_double_soap(soap)
            self.assertTrue(result["bothVerified"])

    def test_inner_verification_fails_closed_without_configured_native_sdk(self):
        with patch.dict("os.environ", {"ISNA_KALKAN_LIBRARY": ""}):
            result = verify_inner_fno_signature_on_vps("<signed/>")
        self.assertFalse(result["cryptoVerifiedOnServer"])
        self.assertEqual(result["cryptoVerificationStatus"], "unavailable")


if __name__ == "__main__":
    unittest.main()
