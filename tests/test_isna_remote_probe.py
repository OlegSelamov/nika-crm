"""Offline-only tests: SSH-based VPN probe never sends or signs a filing."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock

from services import isna_remote_probe as vpn


class IsnaRemoteProbeTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        d = Path(folder.name)
        key = d / "key"
        hosts = d / "known_hosts"
        key.write_text("dummy", encoding="utf-8")
        hosts.write_text("dummy", encoding="utf-8")
        env = patch.dict(os.environ, {
            "APP_MODE": "test",
            "ISNA_BIP_DIAG_SSH_HOST": "195.49.215.49",
            "ISNA_BIP_DIAG_SSH_USER": "isna-probe",
            "ISNA_BIP_DIAG_SSH_KEY": str(key),
            "ISNA_BIP_DIAG_SSH_KNOWN_HOSTS": str(hosts),
        })
        env.start()
        self.addCleanup(env.stop)

    def test_no_arbitrary_external_hosts(self):
        with patch.dict(os.environ, {"ISNA_BIP_DIAG_SSH_HOST": "8.8.8.8"}):
            with patch.object(vpn.subprocess, "run") as run:
                result = vpn.probe_vpn_host()
                self.assertEqual(result["reason"], "bad_config")
                run.assert_not_called()

    def test_disabled_outside_test(self):
        with patch.dict(os.environ, {"APP_MODE": "prod"}):
            with patch.object(vpn.subprocess, "run") as run:
                self.assertFalse(vpn.probe_vpn_host()["ok"])
                run.assert_not_called()

    def test_no_network_when_not_configured(self):
        with patch.dict(os.environ, {"ISNA_BIP_DIAG_SSH_HOST": ""}):
            with patch.object(vpn.subprocess, "run") as run:
                self.assertFalse(vpn.probe_vpn_host()["configured"])
                run.assert_not_called()

    def test_forced_read_only_ssh_options(self):
        response = {"schema": 1, "tcpOk": True, "httpOk": True, "httpStatus": 200}
        with patch.object(vpn.shutil, "which", return_value="/usr/bin/ssh"), \
             patch.object(vpn.subprocess, "run", return_value=Mock(
                 returncode=0, stdout=json.dumps(response), stderr="")) as run:
            result = vpn.probe_vpn_host()
        self.assertTrue(result["tcpOk"])
        self.assertTrue(result["httpOk"])
        args = run.call_args.args[0]
        self.assertEqual(args[-1], "probe")
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("ClearAllForwardings=yes", args)
        self.assertIn("BatchMode=yes", args)
        self.assertEqual(run.call_args.kwargs["input"], "")

    def test_response_rejects_malformed_or_unsafe_data(self):
        with patch.object(vpn.shutil, "which", return_value="/usr/bin/ssh"), \
             patch.object(vpn.subprocess, "run", return_value=Mock(
                 returncode=0, stdout='{"schema":1,"tcpOk":"yes","httpOk":true}', stderr="sensitive")):
            result = vpn.probe_vpn_host()
        self.assertFalse(result["ok"])
        self.assertNotIn("sensitive", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
