"""Offline-only SOAP WS-Security demo structural checks."""
import base64
import unittest

from scripts.isna_inspect_wss import inspect, InvalidSoap, DS, DEMO, SOAP, WSU, WSSE, GOST_SIGNATURE, GOST_DIGEST, EXC_C14N


def make_xml(cer=b"0\x82\xaa\x90" + b"synthetic-cert" * 5, *, ref="#id-12345678", submission="false"):
    cert64 = base64.b64encode(cer).decode()
    return f'''<soap:Envelope xmlns:soap="{SOAP}" xmlns:wsu="{WSU}" xmlns:wsse="{WSSE}" xmlns:ds="{DS}" xmlns:d="{DEMO}">
      <soap:Header><wsse:Security>
        <ds:Signature><ds:SignedInfo>
          <ds:CanonicalizationMethod Algorithm="{EXC_C14N}"/>
          <ds:SignatureMethod Algorithm="{GOST_SIGNATURE}"/>
          <ds:Reference URI="{ref}">
            <ds:Transforms><ds:Transform Algorithm="{EXC_C14N}"/></ds:Transforms>
            <ds:DigestMethod Algorithm="{GOST_DIGEST}"/>
          </ds:Reference>
        </ds:SignedInfo>
        <ds:SignatureValue>ZmFrZQ==</ds:SignatureValue>
        <ds:KeyInfo><ds:X509Data><ds:X509Certificate>{cert64}</ds:X509Certificate></ds:X509Data></ds:KeyInfo>
        </ds:Signature></wsse:Security></soap:Header>
        <soap:Body wsu:Id="id-12345678"><d:NikaWsSecurityTest><d:Submission>{submission}</d:Submission></d:NikaWsSecurityTest></soap:Body>
        </soap:Envelope>'''.encode()


class WssInspectTests(unittest.TestCase):
    cert = b"0\x82\xaa\x90" + b"synthetic-cert" * 5

    def test_valid_structure_and_matching_public_cert(self):
        result = inspect(self.cert, make_xml())
        self.assertTrue(result["structure_ok"])
        self.assertTrue(result["cert_match"])

    def test_wrong_key_public_certificate(self):
        result = inspect(self.cert + b"other", make_xml())
        self.assertFalse(result["cert_match"])

    def test_reference_not_body(self):
        with self.assertRaises(InvalidSoap):
            inspect(self.cert, make_xml(ref="#other"))

    def test_submission_true_rejected(self):
        with self.assertRaises(InvalidSoap):
            inspect(self.cert, make_xml(submission="true"))

    def test_server_generated_offline_bip_shape_supported(self):
        xml = make_xml().decode("utf-8")
        prior = (
            '<soap:Body wsu:Id="id-12345678">'
            '<d:NikaWsSecurityTest><d:Submission>false</d:Submission></d:NikaWsSecurityTest>'
            '</soap:Body>'
        )
        next_body = (
            '<soap:Body wsu:Id="id-12345678">'
            '<typ:SendMessage xmlns:typ="http://bip.bee.kz/SyncChannel/v10/Types">'
            '<request><requestInfo>'
            '<messageId>test-id</messageId>'
            '<serviceId>NIKA_ISNA_OFFLINE_SIGNING_ONLY</serviceId>'
            '<messageDate>2026-10-29T12:00:00+05:00</messageDate>'
            '<sender><senderId>nika-offline-test</senderId></sender>'
            '</requestInfo><requestData><data>'
            '<d:NikaWsSecurityTest><d:Submission>false</d:Submission></d:NikaWsSecurityTest>'
            '</data></requestData></request></typ:SendMessage></soap:Body>'
        )
        self.assertIn(prior, xml)
        checked = inspect(self.cert, xml.replace(prior, next_body).encode("utf-8"))
        self.assertTrue(checked["cert_match"])
        self.assertEqual(checked["sample_type"], "test-server-bip-demo")
        with self.assertRaises(InvalidSoap):
            inspect(self.cert, xml.replace(prior, next_body.replace(
                "NIKA_ISNA_OFFLINE_SIGNING_ONLY", "FNO_INTEGRATION",
            )).encode("utf-8"))

    def test_normal_nika_soap_without_signature_rejected(self):
        with self.assertRaises(InvalidSoap):
            inspect(self.cert, b'<soap:Envelope xmlns:soap="' + SOAP.encode() + b'"/>')

if __name__ == "__main__":
    unittest.main()
