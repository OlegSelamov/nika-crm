"""Public transport certificate pinning for ISNA TEST (no private keys).

Only public .cer/.crt/.pem/.der files or the operator configured SHA-256
fingerprint can establish the EXPECTED signer identity. This does NOT
establish government registration, revocation status, or taxpayer authority.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

from scripts.isna_inspect_wss import InvalidSoap, decode_cert

PUBLIC_SUFFIXES = {".cer", ".crt", ".pem", ".der"}
MAX_CERT_BYTES = 65536


def registered_transport_certificate_sha256() -> str | None:
    """Return operator-configured public cert identity or None.

    File and hash configured together MUST agree. Fail closed on invalid
    formats/symlinks/absence of configured public file: never silently
    downgrade a supposedly registered transport certificate to "unknown".
    """
    configured_hash = (os.getenv("ISNA_BIP_REGISTERED_CERT_SHA256") or "").strip()
    configured_hash = configured_hash.replace(":", "").upper()
    if configured_hash and not re.fullmatch(r"[A-F0-9]{64}", configured_hash):
        raise InvalidSoap("Invalid registered transport certificate SHA-256.")
    path_value = (os.getenv("ISNA_BIP_REGISTERED_CERT_PATH") or "").strip()
    if not path_value:
        return configured_hash or None
    path = Path(path_value)
    if (not path.is_absolute() or path.suffix.lower() not in PUBLIC_SUFFIXES
            or path.is_symlink() or not path.is_file()):
        raise InvalidSoap("Invalid public registered transport certificate path.")
    try:
        if not 0 < path.stat().st_size <= MAX_CERT_BYTES:
            raise InvalidSoap("Invalid public registered transport certificate size.")
        encoded = path.read_bytes()
    except OSError as exc:
        raise InvalidSoap("Cannot read registered public transport certificate.") from exc
    der = decode_cert(encoded)
    if len(der) > MAX_CERT_BYTES:
        raise InvalidSoap("Registered public transport certificate exceeds limit.")
    fingerprint = hashlib.sha256(der).hexdigest().upper()
    if configured_hash and configured_hash != fingerprint:
        raise InvalidSoap("Configured transport certificate pin disagrees with .cer.")
    return fingerprint
