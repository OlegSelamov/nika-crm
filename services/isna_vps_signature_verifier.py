"""Offline, independent VPS XMLDSig check for the inert ISNA TEST SOAP.

The public X.509 DER is extracted from the SOAP (no .p12 or secret needed).
This requires an xmlsec1 build with the Kazakhstan GOST 2015-512 XML
signature + digest algorithms enabled. A stock xmlsec1 may lack GOST.
Unsupported/missing verifier is reported as NOT VERIFIED, never as success.

Only call after the strict non-filing SOAP structural validator. This verifier
never sends a network request, logs the SOAP, or writes persistent artifacts.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

GOST_TRANSFORM = "gostr34102015-gostr34112015-512"
TIMEOUT_SECONDS = 10


def verify_soap_signature_on_vps(signed_xml: str, signer_cert_der: bytes) -> dict:
    """Verify both SignedInfo signature and Body Reference digest via xmlsec1.

    Cryptographic validity proves possession of the corresponding signing
    key, not registration in Smart Bridge, certificate-chain trust or
    revocation status. Caller compares the embedded public certificate with
    the expected SHA-256 fingerprint or public .cer independently.
    """
    executable = (os.getenv("ISNA_XMLSEC1_BIN") or "xmlsec1").strip()
    if not executable or not shutil.which(executable):
        return {
            "cryptoVerifiedOnServer": False,
            "cryptoVerificationStatus": "unavailable",
            "cryptoVerifier": "xmlsec1",
        }
    try:
        supported = subprocess.run(
            [executable, "--list-transforms"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "cryptoVerifiedOnServer": False,
            "cryptoVerificationStatus": "unavailable",
            "cryptoVerifier": "xmlsec1",
        }

    transforms = (supported.stdout or "") + (supported.stderr or "")
    if supported.returncode != 0 or GOST_TRANSFORM not in transforms.lower():
        return {
            "cryptoVerifiedOnServer": False,
            "cryptoVerificationStatus": "unsupported",
            "cryptoVerifier": "xmlsec1",
        }

    try:
        # Both files are private, short-lived and outside the web application.
        with tempfile.TemporaryDirectory(prefix="nika-isna-verify-") as temp:
            soap_path = Path(temp) / "signed-soap.xml"
            cert_path = Path(temp) / "signer-public.der"
            soap_path.write_bytes(signed_xml.encode("utf-8"))
            cert_path.write_bytes(signer_cert_der)
            os.chmod(soap_path, 0o600)
            os.chmod(cert_path, 0o600)
            command = [
                executable,
                "--verify",
                "--enabled-reference-uris", "same-doc",
                "--enabled-retrieval-method-uris", "same-doc",
                "--enabled-key-info-reference-uris", "same-doc",
                "--node-name", "http://www.w3.org/2000/09/xmldsig#:Signature",
                "--id-attr:Id", "http://schemas.xmlsoap.org/soap/envelope/:Body",
                "--lax-key-search",
                "--pubkey-cert-der", str(cert_path),
                str(soap_path),
            ]
            completed = subprocess.run(
                command, capture_output=True, text=True,
                timeout=TIMEOUT_SECONDS, check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "cryptoVerifiedOnServer": False,
            "cryptoVerificationStatus": "error",
            "cryptoVerifier": "xmlsec1",
        }

    # Never forward stdout/stderr from the GOST verifier to Android: they can
    # include paths or untrusted document data. Exit 0 is success; all other
    # results fail closed. --list-transforms screened unsupported builds.
    valid = completed.returncode == 0
    return {
        "cryptoVerifiedOnServer": valid,
        "cryptoVerificationStatus": "verified" if valid else "invalid",
        "cryptoVerifier": "xmlsec1",
    }
