#!/usr/bin/env python3
"""Calculate Nika ISNA registered transport certificate SHA-256 locally.

Only PUBLIC X.509 .cer/.crt/.pem/.der, never private P12/PFX/passwords.
Does NOT upload certificate, change .env or contact the network.
Example:
  python3 scripts/isna_transport_public_cert.py /private/public/registered.cer
Then the administrator must verify this is actually the certificate
registered in Smart Bridge before putting the result in TEST .env.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from scripts.isna_inspect_wss import InvalidSoap, decode_cert


def public_fingerprint(path: Path) -> str:
    if not path.is_file() or path.is_symlink() or path.suffix.lower() not in (
            ".cer", ".crt", ".pem", ".der"):
        raise ValueError("Expected an ordinary PUBLIC .cer/.crt/.pem/.der file.")
    if not 0 < path.stat().st_size <= 65536:
        raise ValueError("Invalid public certificate file size.")
    raw = decode_cert(path.read_bytes())
    if not 64 <= len(raw) <= 65536:
        raise ValueError("Not a plausible X.509 public certificate.")
    return hashlib.sha256(raw).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description="Print SHA-256 of the registered PUBLIC transport certificate")
    parser.add_argument("public_certificate", type=Path)
    args = parser.parse_args()
    try:
        sha = public_fingerprint(args.public_certificate)
    except (ValueError, OSError, InvalidSoap):
        print("Invalid public certificate; NO private key is accepted.", file=sys.stderr)
        return 2
    print("ISNA_BIP_REGISTERED_CERT_SHA256=" + sha)
    print("Confirm the .cer belongs to the system's Smart Bridge registration before using this value.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
