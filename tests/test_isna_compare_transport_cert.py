"""Offline tests for Smart Bridge public certificate comparison."""
import base64
import unittest

from scripts.isna_compare_transport_cert import (
    InvalidCertificateInput, compare_certificates,
)


def example_xml(cer: bytes) -> bytes:
    encoded = base64.b64encode(cer).decode("ascii")
    return (
        '<Root xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
        '<ds:Signature><ds:KeyInfo><ds:X509Data>'
        f'<ds:X509Certificate>{encoded}</ds:X509Certificate>'
        '</ds:X509Data></ds:KeyInfo></ds:Signature></Root>'
    ).encode("utf-8")


class IsnaCertificateComparisonTests(unittest.TestCase):
    # Synthetic DER-shaped blobs; not real keys, not cryptographic validation.
    example_der = b"0\x82\x01\x00" + b"certificate-one" * 6
    another_der = b"0\x82\x01\x00" + b"certificate-two" * 6

    def test_der_cer_matches_xml_base64(self):
        same, first, embedded = compare_certificates(
            self.example_der, example_xml(self.example_der)
        )
        self.assertTrue(same)
        self.assertEqual(first, embedded[0])

    def test_pem_cer_matches_xml_base64(self):
        pem = (b"-----BEGIN CERTIFICATE-----\n"
               + base64.b64encode(self.example_der)
               + b"\n-----END CERTIFICATE-----\n")
        self.assertTrue(compare_certificates(pem, example_xml(self.example_der))[0])

    def test_different_certificate_detected(self):
        same, first, embedded = compare_certificates(
            self.example_der, example_xml(self.another_der)
        )
        self.assertFalse(same)
        self.assertNotEqual(first, embedded[0])

    def test_unsigned_xml_rejected(self):
        with self.assertRaises(InvalidCertificateInput):
            compare_certificates(self.example_der, b"<root/>")

    def test_invalid_embedded_base64_rejected(self):
        with self.assertRaises(InvalidCertificateInput):
            compare_certificates(
                self.example_der,
                example_xml(self.example_der).replace(
                    base64.b64encode(self.example_der), b"!invalid!"
                ),
            )


if __name__ == "__main__":
    unittest.main()
