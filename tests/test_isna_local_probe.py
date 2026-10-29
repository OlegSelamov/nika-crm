"""Offline tests for fixed-target local IPsec gateway probe (no network)."""
import socket
import unittest
from unittest.mock import MagicMock, patch

from scripts import isna_gateway_probe as probe


class LocalIsnaProbeTests(unittest.TestCase):
    def test_local_bind_detects_source_ip(self):
        with patch.object(probe.socket, "socket") as sock_ctor:
            self.assertTrue(probe.local_source_available())
            sock_ctor.return_value.__enter__.return_value.bind.assert_called_once_with(
                ("195.49.215.49", 0)
            )

    def test_local_bind_denied_on_different_host(self):
        with patch.object(probe.socket, "socket") as sock_ctor:
            sock_ctor.return_value.__enter__.return_value.bind.side_effect = OSError(
                "Cannot assign requested address"
            )
            self.assertFalse(probe.local_source_available())

    def test_probe_only_fixed_source_fixed_target_and_http_get(self):
        connection = MagicMock()
        response = MagicMock(status=200)
        connection.getresponse.return_value = response
        with patch.object(probe.socket, "create_connection") as tcp, \
             patch.object(probe.http.client, "HTTPConnection", return_value=connection) as http:
            result = probe.probe_gateway()
        self.assertEqual(result, {
            "schema": 1, "tcpOk": True, "httpOk": True, "httpStatus": 200
        })
        tcp.assert_called_once_with(
            ("195.12.113.7", 80), timeout=5,
            source_address=("195.49.215.49", 0),
        )
        http.assert_called_once_with(
            "195.12.113.7", 80, timeout=5,
            source_address=("195.49.215.49", 0),
        )
        connection.request.assert_called_once_with(
            "GET", "/bip-sync-wss-gost/", headers={"Accept": "text/xml"}
        )

    def test_tcp_failure_never_sends_http(self):
        with patch.object(probe.socket, "create_connection", side_effect=OSError), \
             patch.object(probe.http.client, "HTTPConnection") as http:
            result = probe.probe_gateway()
        self.assertFalse(result["tcpOk"])
        http.assert_not_called()


if __name__ == "__main__":
    unittest.main()
