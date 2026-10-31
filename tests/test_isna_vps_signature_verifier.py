"""No-network tests for the independent TEST VPS cryptographic verifier."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch, Mock

from services.isna_vps_signature_verifier import (
    GOST_TRANSFORM, verify_soap_signature_on_vps,
)


class VpsGostVerifierTests(unittest.TestCase):
    def test_missing_binary_fails_closed(self):
        with patch("services.isna_vps_signature_verifier.shutil.which", return_value=None):
            result = verify_soap_signature_on_vps("<signed/>", b"cert")
        self.assertFalse(result["cryptoVerifiedOnServer"])
        self.assertEqual(result["cryptoVerificationStatus"], "unavailable")

    def test_no_gost_support_fails_closed_without_verifying(self):
        with patch("services.isna_vps_signature_verifier.shutil.which", return_value="/usr/bin/xmlsec1"), \
             patch("services.isna_vps_signature_verifier.subprocess.run", return_value=Mock(
                 returncode=0, stdout="rsa-sha256", stderr=""
             )) as run:
            result = verify_soap_signature_on_vps("<signed/>", b"cert")
        self.assertFalse(result["cryptoVerifiedOnServer"])
        self.assertEqual(result["cryptoVerificationStatus"], "unsupported")
        self.assertEqual(run.call_count, 1)

    def test_gost_verifier_checks_exact_xml_against_embedded_public_cert(self):
        soap = "<Envelope>signed exactly as received</Envelope>"
        cert = b"\x30\x82\x00\x02"
        def fake_run(argv, **kwargs):
            if "--list-transforms" in argv:
                return Mock(returncode=0, stdout=GOST_TRANSFORM, stderr="")
            self.assertIn("--verify", argv)
            self.assertIn("--enabled-reference-uris", argv)
            self.assertIn("same-doc", argv)
            self.assertIn("--id-attr:Id", argv)
            self.assertIn("--pubkey-cert-der", argv)
            self.assertEqual(Path(argv[-1]).read_bytes(), soap.encode("utf-8"))
            self.assertEqual(Path(argv[argv.index("--pubkey-cert-der") + 1]).read_bytes(), cert)
            self.assertNotIn("--insecure", argv)
            self.assertNotIn("--xxe", argv)
            return Mock(returncode=0, stdout="OK", stderr="")
        with patch("services.isna_vps_signature_verifier.shutil.which", return_value="/usr/bin/xmlsec1"), \
             patch("services.isna_vps_signature_verifier.subprocess.run", side_effect=fake_run):
            result = verify_soap_signature_on_vps(soap, cert)
        self.assertTrue(result["cryptoVerifiedOnServer"])
        self.assertEqual(result["cryptoVerificationStatus"], "verified")

    def test_signature_invalid_is_not_success(self):
        with patch("services.isna_vps_signature_verifier.shutil.which", return_value="/usr/bin/xmlsec1"), \
             patch("services.isna_vps_signature_verifier.subprocess.run", side_effect=[
                 Mock(returncode=0, stdout=GOST_TRANSFORM, stderr=""),
                 Mock(returncode=1, stdout="FAIL", stderr=""),
             ]):
            result = verify_soap_signature_on_vps("<signed/>", b"cert")
        self.assertFalse(result["cryptoVerifiedOnServer"])
        self.assertEqual(result["cryptoVerificationStatus"], "invalid")

    def test_timeout_never_reports_valid(self):
        with patch("services.isna_vps_signature_verifier.shutil.which", return_value="/usr/bin/xmlsec1"), \
             patch("services.isna_vps_signature_verifier.subprocess.run", side_effect=subprocess.TimeoutExpired("xmlsec1", 4)):
            result = verify_soap_signature_on_vps("<signed/>", b"cert")
        self.assertFalse(result["cryptoVerifiedOnServer"])
        self.assertEqual(result["cryptoVerificationStatus"], "unavailable")


if __name__ == "__main__":
    unittest.main()
