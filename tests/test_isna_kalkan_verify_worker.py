"""No native library is executed in these KalkanCrypt worker contract tests."""
import ctypes
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from services.isna_kalkan_verify_worker import verify_native


class KalkanWorkerTests(unittest.TestCase):
    def test_calls_linux_verifyxml_with_in_memory_xml_without_keystore(self):
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder) / "libkalkancryptwr-64.so.2.0.14"
            library.write_bytes(b"mock-library-not-executable")
            mock_api = Mock()
            mock_api.Init.return_value = 0
            mock_api.VerifyXML.return_value = 0
            with patch("services.isna_kalkan_verify_worker.ctypes.CDLL", return_value=mock_api):
                self.assertTrue(verify_native(b"<signed/>", str(library)))
            mock_api.Init.assert_called_once_with()
            mock_api.VerifyXML.assert_called_once()
            args = mock_api.VerifyXML.call_args.args
            self.assertEqual(args[0], b"")
            self.assertEqual(args[1], 0)
            self.assertIsInstance(args[2], ctypes.c_void_p)
            self.assertEqual(args[3], len(b"<signed/>"))
            mock_api.KC_LoadKeyStore.assert_not_called()

    def test_bad_signature_is_false_even_when_library_loads(self):
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder) / "libkalkancryptwr-64.so.2.0.14"
            library.write_bytes(b"mock-library-not-executable")
            mock_api = Mock()
            mock_api.Init.return_value = 0
            mock_api.VerifyXML.return_value = 3
            with patch("services.isna_kalkan_verify_worker.ctypes.CDLL", return_value=mock_api):
                self.assertFalse(verify_native(b"<signed/>", str(library)))

    def test_missing_binary_and_excess_xml_are_rejected(self):
        with self.assertRaises(ValueError):
            verify_native(b"<signed/>", "/no/such/kalkan.so")
        with self.assertRaises(ValueError):
            verify_native(b"a" * 256001, "/no/such/kalkan.so")


if __name__ == "__main__":
    unittest.main()
