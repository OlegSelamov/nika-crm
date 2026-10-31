"""No-network contract tests for private public CA ZIP installer."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import install_isna_kalkan_trust as installer


class TrustArchiveTests(unittest.TestCase):
    def test_only_expected_certificates_installed_outside_global_store(self):
        fixtures = {
            "root_gost_2022.pem": b"-----BEGIN CERTIFICATE-----\\nROOT\\n-----END CERTIFICATE-----\\n",
            "nca_gost_2022.pem": b"-----BEGIN CERTIFICATE-----\\nNCA\\n-----END CERTIFICATE-----\\n",
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "production2022.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                for name, data in fixtures.items():
                    zipped.writestr(installer.SOURCE_PREFIX + name, data)
                zipped.writestr("production2022/production/evil.pem", b"not trusted")
            expected_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in fixtures.items()}
            with patch.object(installer, "EXPECTED_SHA256", expected_hashes):
                destination = root / "trust"
                names = installer.install_from_zip(archive, destination)
            self.assertEqual(names, sorted(fixtures))
            for name, data in fixtures.items():
                self.assertEqual((destination / name).read_bytes(), data)
            self.assertFalse((destination / "evil.pem").exists())

    def test_wrong_certificate_rejected_without_any_installs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "production2022.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                for name in installer.EXPECTED_SHA256:
                    zipped.writestr(installer.SOURCE_PREFIX + name, b"bad cert")
            target = root / "trust"
            with self.assertRaises(ValueError):
                installer.install_from_zip(archive, target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
