"""No-network tests for public registered signer pin and offline-only CLI."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.isna_inspect_wss import InvalidSoap
from services.isna_transport_certificate import registered_transport_certificate_sha256
from services.isna_double_fno_offline import compare_certificate_roles
from services.isna_transport_signer_cli import (
    SigningUnavailable, _private_key_location, sign_test_soap_native,
)


class TransportCertificateTests(unittest.TestCase):
    def test_no_pin_is_unknown_not_an_authorization(self):
        with patch.dict(os.environ, {"ISNA_BIP_REGISTERED_CERT_SHA256": "",
                                     "ISNA_BIP_REGISTERED_CERT_PATH": ""}):
            self.assertIsNone(registered_transport_certificate_sha256())
            result = compare_certificate_roles(b"taxpayer", b"transport")
            self.assertIsNone(result["transportCertMatchesConfiguredPin"])
            self.assertFalse(result["transportCertificateIdentityReady"])
            self.assertFalse(result["taxpayerAuthorityChecked"])

    def test_fingerprint_only_and_same_cert_are_not_distinct_signers(self):
        transport = b"\x30\x82public-cert"
        sha = hashlib.sha256(transport).hexdigest().upper()
        with patch.dict(os.environ, {"ISNA_BIP_REGISTERED_CERT_SHA256": sha,
                                     "ISNA_BIP_REGISTERED_CERT_PATH": ""}):
            result = compare_certificate_roles(b"taxpayer", transport)
            self.assertTrue(result["transportCertMatchesConfiguredPin"])
            self.assertTrue(result["transportCertificateIdentityReady"])
            same = compare_certificate_roles(transport, transport)
            self.assertTrue(same["transportCertMatchesConfiguredPin"])
            self.assertFalse(same["transportCertificateIdentityReady"])

    def test_public_certificate_file_fingerprint_and_conflicting_pin(self):
        # decode_cert treats DER beginning with ASN.1 sequence marker and
        # high-byte content in the first bytes as an opaque public cert.
        sample = b"\x30\x82" + b"public-der-binary" * 8
        fingerprint = hashlib.sha256(sample).hexdigest().upper()
        with tempfile.TemporaryDirectory() as folder:
            cert = Path(folder) / "registered.cer"
            cert.write_bytes(sample)
            with patch.dict(os.environ, {"ISNA_BIP_REGISTERED_CERT_SHA256": "",
                                         "ISNA_BIP_REGISTERED_CERT_PATH": str(cert)}):
                self.assertEqual(registered_transport_certificate_sha256(), fingerprint)
            with patch.dict(os.environ, {"ISNA_BIP_REGISTERED_CERT_SHA256": "0"*64,
                                         "ISNA_BIP_REGISTERED_CERT_PATH": str(cert)}):
                with self.assertRaises(InvalidSoap):
                    registered_transport_certificate_sha256()
            link = Path(folder) / "alias.cer"
            link.symlink_to(cert)
            with patch.dict(os.environ, {"ISNA_BIP_REGISTERED_CERT_PATH": str(link),
                                         "ISNA_BIP_REGISTERED_CERT_SHA256": ""}):
                with self.assertRaises(InvalidSoap):
                    registered_transport_certificate_sha256()
            with patch.dict(os.environ, {"ISNA_BIP_REGISTERED_CERT_PATH": "",
                                         "ISNA_BIP_REGISTERED_CERT_SHA256": "not-a-sha"}):
                with self.assertRaises(InvalidSoap):
                    registered_transport_certificate_sha256()

    def test_secret_key_path_policy_and_no_web_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "dedicated-transport.p12"
            key.write_bytes(b"opaque P12 test fixture")
            key.chmod(0o644)
            with self.assertRaises(SigningUnavailable):
                _private_key_location(key)
            key.chmod(0o600)
            if os.geteuid() == 0:
                with self.assertRaisesRegex(SigningUnavailable, "root"):
                    _private_key_location(key)
            else:
                _private_key_location(key)
            link = Path(folder) / "alias.p12"
            link.symlink_to(key)
            with self.assertRaises(SigningUnavailable):
                _private_key_location(link)

    def test_native_signing_never_runs_with_unsigned_empty_xml(self):
        with self.assertRaises(SigningUnavailable):
            sign_test_soap_native(b"", library="/unused.so",
                                  key_path=Path("/missing/key.p12"),
                                  password=b"secret", body_id="id-demo123")

    def test_cli_does_not_provide_flask_api_or_gateway_method(self):
        import services.isna_transport_signer_cli as signer
        self.assertFalse(hasattr(signer, "post_signed_envelope"))
        self.assertFalse(hasattr(signer, "send_synthetic_signed_soap"))


if __name__ == "__main__":
    unittest.main()
