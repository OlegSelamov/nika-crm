"""No-network tests for public registered signer pin and offline-only CLI."""
import ctypes
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

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

    def test_native_sign_uses_exclusive_c14n_and_only_dedicated_p12(self):
        native = MagicMock()
        native.Init.return_value = 0
        native.KC_LoadKeyStore.return_value = 0
        soap_out = b"<soap:Envelope>inert-signed-test</soap:Envelope>"
        def produce_wsse(alias, flags, data, input_size, out, out_size, node_id):
            self.assertEqual(flags, 0x01000010)
            self.assertEqual(node_id, b"id-test-1234")
            self.assertEqual(data, b"<soap/>")
            self.assertEqual(input_size, len(data))
            ctypes.memmove(out, soap_out, len(soap_out))
            ctypes.cast(out_size, ctypes.POINTER(ctypes.c_int)).contents.value = len(soap_out)
            return 0
        native.SignWSSE.side_effect = produce_wsse
        with patch("services.isna_transport_signer_cli.ctypes.CDLL", return_value=native), \\
             patch("services.isna_transport_signer_cli._private_key_location"), \\
             patch("pathlib.Path.is_file", return_value=True), \\
             patch("pathlib.Path.is_symlink", return_value=False):
            signed, load_code, sign_code = sign_test_soap_native(
                b"<soap/>", library="/opt/nika/kalkan/libkalkancryptwr-64.so.2.0.14",
                key_path=Path("/private/key.p12"),
                password=b"test-only-not-a-real-password", body_id="id-test-1234",
            )
        self.assertEqual(signed, soap_out)
        self.assertEqual((load_code, sign_code), ("0x00000000", "0x00000000"))
        self.assertEqual(native.KC_LoadKeyStore.call_count, 1)
        self.assertEqual(native.SignWSSE.call_count, 1)
        native.KC_Finalize.assert_called_once()

    def test_cli_does_not_provide_flask_api_or_gateway_method(self):
        import services.isna_transport_signer_cli as signer
        self.assertFalse(hasattr(signer, "post_signed_envelope"))
        self.assertFalse(hasattr(signer, "send_synthetic_signed_soap"))


if __name__ == "__main__":
    unittest.main()
