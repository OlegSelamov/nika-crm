"""All real-FNO TEST submission tests are offline: no private keys or POSTs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from services import isna_real_fno_submission as real


def _signed_sample():
    # Syntactic-only fixture: cryptography is mocked and no real FNO is sent.
    return (
        '<root><data>{"code":"910.00","fnoDto":{"nikaFake":true}}</data>'
        '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
        '<ds:SignedInfo><ds:Reference URI=""/></ds:SignedInfo>'
        '<ds:SignatureValue>FAKE_FOR_OFFLINE_TESTS</ds:SignatureValue>'
        '</ds:Signature></root>'
    )


def _service_response(success=True):
    return (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
        ' xmlns:typ="http://bip.bee.kz/SyncChannel/v10/Types">'
        '<soap:Body><typ:SendMessageResponse><response><responseInfo>'
        '<status><code>OK</code></status></responseInfo>'
        '<responseData><data>{"success":' + ("true" if success else "false")
        + ',"fno_id":42}</data></responseData></response>'
        '</typ:SendMessageResponse></soap:Body></soap:Envelope>'
    ).encode()


class RealFnoSubmissionTests(unittest.TestCase):
    def test_real_filing_off_by_default_even_in_test(self):
        with patch.dict(os.environ, {"APP_MODE": "test"}, clear=True), \
             patch.object(real, "local_source_available") as vpn, \
             patch.object(real.http.client, "HTTPConnection") as connection:
            with self.assertRaisesRegex(real.FnoSubmissionBlocked, "disabled"):
                real._test_config()
            vpn.assert_not_called()
            connection.assert_not_called()

    def test_prod_cannot_be_enabled_by_env_flag(self):
        with patch.dict(os.environ, {
            "APP_MODE": "prod", real.FLAG: "1",
        }, clear=True), patch.object(real.http.client, "HTTPConnection") as connection:
            with self.assertRaises(real.FnoSubmissionBlocked):
                real._test_config()
            connection.assert_not_called()

    def test_reject_invalid_explicit_confirmations(self):
        with self.assertRaises(real.FnoSubmissionBlocked):
            real._clean_pin("not-a-sha256")
        with self.assertRaises(real.FnoSubmissionBlocked):
            real.submit_test_fno(SimpleNamespace(confirm="YES", expected_code="910.00"))
        with self.assertRaises(real.FnoSubmissionBlocked):
            real.submit_test_fno(SimpleNamespace(
                confirm=real.SEND_CONFIRMATION, expected_code="000.00"
            ))

    def test_response_is_never_accepted_on_http_status_alone(self):
        successful = real._interpret_reply(200, _service_response(), False)
        self.assertEqual(successful["outcome"], "service-reported-success")
        self.assertEqual(successful["fnoId"], "42")
        self.assertEqual(
            real._interpret_reply(500, _service_response(), False)["outcome"], "unknown"
        )
        self.assertEqual(
            real._interpret_reply(200, _service_response(False), False)["outcome"], "rejected"
        )
        self.assertEqual(
            real._interpret_reply(200, _service_response(), True)["outcome"], "unknown"
        )
        fault = (b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                 b'<s:Body><s:Fault><faultcode>Client</faultcode>'
                 b'<faultstring>Rejected</faultstring></s:Fault></s:Body></s:Envelope>')
        self.assertEqual(real._interpret_reply(500, fault, False)["outcome"], "rejected")

    def test_journal_claim_is_exclusive_and_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / "only-once.json"
            real._write_journal(path, {"state": "prepared"}, first=True)
            with self.assertRaises(real.FnoSubmissionBlocked):
                real._write_journal(path, {"state": "prepared"}, first=True)
            real._write_journal(path, {"state": "attempted"})
            self.assertEqual(json.loads(path.read_text())["state"], "attempted")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_transport_body_unchanged_and_real_service_only(self):
        fno = _signed_sample()
        from services.isna_fno_integration import build_fno_integration_soap
        envelope = build_fno_integration_soap(
            fno, sender_id="nika-registered-test", message_id="fixed-uuid",
        )
        with patch.object(real, "extract_signer_certificate", return_value=(b"certificate", "key-identifier")):
            self.assertEqual(
                real._assert_signed_body(envelope, fno, "nika-registered-test", "fixed-uuid"),
                b"certificate",
            )
            with self.assertRaises(real.FnoSubmissionBlocked):
                real._assert_signed_body(envelope, fno + "modified", "nika-registered-test", "fixed-uuid")
            with self.assertRaises(real.FnoSubmissionBlocked):
                real._assert_signed_body(envelope, fno, "wrong-sender", "fixed-uuid")

    def _run_mocked(self, journal_dir, *, post_reply=None, raises=None):
        fno = _signed_sample()
        digest = hashlib.sha256(fno.encode()).hexdigest().upper()
        args = SimpleNamespace(
            confirm=real.SEND_CONFIRMATION,
            expected_code="910.00",
            confirm_payload_sha256=digest,
            taxpayer_cert_sha256="AA" * 32,
            journal_dir=journal_dir,
            transport_key=Path("/nonexistent/transport.p12"),
            signed_fno=Path("/nonexistent/signed-fno.xml"),
        )
        cfg = SimpleNamespace(sender_id="nika-registered-test", sender_password="")
        post = (patch.object(real, "_post_to_test", side_effect=raises) if raises
                else patch.object(real, "_post_to_test", return_value=(200, post_reply or _service_response(), False)))
        with patch.object(real, "_private_key_location"), \
             patch.object(real, "_test_config", return_value=(cfg, hashlib.sha256(b"transport").hexdigest().upper(), "/fake/kalkan.so")), \
             patch.object(real, "_private_input", return_value=fno), \
             patch.object(real, "_taxpayer_certificate_pin", return_value="AA" * 32), \
             patch.object(real, "verify_inner_fno_signature_on_vps", return_value={"cryptoVerifiedOnServer": True}), \
             patch.object(real, "sign_test_soap_native", return_value=(b"<mocked-signed-soap/>", "", "")), \
             patch.object(real, "_assert_signed_body", return_value=b"transport"), \
             patch.object(real, "verify_soap_signature_on_vps", return_value={"cryptoVerifiedOnServer": True}), \
             patch.object(real.getpass, "getpass", return_value="never-a-real-password"), \
             post as post_mock:
            if raises:
                with self.assertRaises(real.FnoSubmissionBlocked):
                    real.submit_test_fno(args)
                return digest, post_mock.call_count
            result = real.submit_test_fno(args)
            return result, post_mock.call_count

    def test_one_genuine_submission_path_records_service_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, count = self._run_mocked(Path(tmp))
            self.assertEqual(count, 1)
            self.assertEqual(result["state"], "service-reported-success")
            record = json.loads(Path(result["journal"]).read_text())
            self.assertEqual(record["state"], "service-reported-success")
            self.assertEqual(record["messageId"], result["messageId"])
            # Never store tax figures, XML, certificate bytes, or P12 secrets.
            self.assertNotIn("<root>", json.dumps(record))
            self.assertNotIn("never-a-real-password", json.dumps(record))
            with self.assertRaises(real.FnoSubmissionBlocked):
                self._run_mocked(Path(tmp))

    def test_network_unknown_never_retries_or_erases_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            digest, count = self._run_mocked(
                Path(tmp), raises=real.FnoSubmissionBlocked("network outcome unknown")
            )
            self.assertEqual(count, 1)
            record = json.loads((Path(tmp) / (digest.lower() + ".json")).read_text())
            self.assertEqual(record["state"], "attempted")
            with self.assertRaises(real.FnoSubmissionBlocked):
                self._run_mocked(Path(tmp))


if __name__ == "__main__":
    unittest.main()
