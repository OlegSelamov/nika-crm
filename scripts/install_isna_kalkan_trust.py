"""Install only the two official 2022 GOST public CA PEMs for ISNA TEST.

Usage (on TEST VPS, as root):
  sudo python3 scripts/install_isna_kalkan_trust.py /home/ubuntu/production2022.zip

No shell scripts from ZIP run. No updates to /etc/ssl or global CA trust.
Public PEMs stay outside the Flask app, in /opt/nika/kalkan/trust/.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import zipfile

DEST = Path("/opt/nika/kalkan/trust")
SOURCE_PREFIX = "production2022/production/"
EXPECTED_SHA256 = {
    "root_gost_2022.pem": "91dcd1090a829f776af5a0581baec4a0f1f9c01e4016e073ecc2666b94843135",
    "nca_gost_2022.pem": "569c840010abab9aa9a7985047aa6438afa1440a8f55e7c4b426dc1a76b64ac9",
}


def install_from_zip(zip_file: Path, destination: Path = DEST) -> list[str]:
    if destination.is_symlink():
        raise ValueError("Refusing symlink CA directory")
    if not destination.parent.is_dir():
        raise ValueError("KalkanCrypt library directory is missing")
    verified = {}
    with zipfile.ZipFile(zip_file) as archive:
        for name, expected_hash in EXPECTED_SHA256.items():
            data = archive.read(SOURCE_PREFIX + name)
            if not 0 < len(data) < 32768:
                raise ValueError(f"Invalid certificate size: {name}")
            if hashlib.sha256(data).hexdigest() != expected_hash:
                raise ValueError(f"Wrong or modified CA certificate: {name}")
            if b"-----BEGIN CERTIFICATE-----" not in data or b"-----END CERTIFICATE-----" not in data:
                raise ValueError(f"Invalid PEM certificate: {name}")
            verified[name] = data
    destination.mkdir(mode=0o755, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("Refusing symlink CA directory")
    for name, data in verified.items():
        target = destination / name
        if target.is_symlink():
            raise ValueError(f"Refusing symlink CA: {name}")
        fd, temporary = tempfile.mkstemp(prefix=".isna-ca-", dir=destination)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return sorted(verified)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python install_isna_kalkan_trust.py ZIPFILE")
    for name in install_from_zip(Path(sys.argv[1])):
        print("Installed TEST-only public CA:", name)
    print("No system CA trust store was changed.")
