"""Offline, independent VPS XMLDSig check for the inert ISNA TEST SOAP.

The public X.509 DER is extracted from the SOAP (no .p12 or secret needed).
This requires an xmlsec1 build with the Kazakhstan GOST 2015-512 XML
signature + digest algorithms enabled. A stock xmlsec1 may lack GOST.
Unsupported/missing verifier is reported as NOT VERIFIED, never as success.

Only call after the strict non-filing SOAP structural validator. This verifier
never sends a network request, logs the SOAP, or writes persistent artifacts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

GOST_TRANSFORM = "gostr34102015-gostr34112015-512"
TIMEOUT_SECONDS = 10
_KALKAN_PROTOCOL = "NIKA_KALKAN_XML_VERIFY_V1:"


def _verify_with_kalkan(signed_xml: str) -> dict:
    """Run native KalkanCrypt in a child, never the Gunicorn process.

    Configuration is opt-in. A crash, timeout, missing SDK dependency or
    malformed worker result fails closed and never unlocks a TEST POST.
    """
    result_prefix = {
        "cryptoVerifiedOnServer": False,
        "cryptoVerifier": "KalkanCrypt",
    }
    worker = Path(__file__).with_name("isna_kalkan_verify_worker.py")
    try:
        completed = subprocess.run(
            [sys.executable, str(worker)],
            input=signed_xml.encode("utf-8"),
            capture_output=True, timeout=TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {**result_prefix, "cryptoVerificationStatus": "error"}
    if completed.returncode != 0 or len(completed.stdout) > 8192:
        return {**result_prefix, "cryptoVerificationStatus": "error"}
    # SDK may write its own harmless log line; parse only our explicit protocol
    # record and never expose native text to Android or logs.
    status_lines = [
        line for line in completed.stdout.decode("utf-8", errors="replace").splitlines()
        if line.startswith(_KALKAN_PROTOCOL)
    ]
    if len(status_lines) != 1:
        return {**result_prefix, "cryptoVerificationStatus": "error"}
    try:
        result = json.loads(status_lines[0][len(_KALKAN_PROTOCOL):])
    except (ValueError, TypeError):
        return {**result_prefix, "cryptoVerificationStatus": "error"}
    status = result.get("status") if isinstance(result, dict) else None
    if status not in ("verified", "invalid", "unavailable", "error"):
        status = "error"
    return {
        **result_prefix,
        "cryptoVerifiedOnServer": status == "verified",
        "cryptoVerificationStatus": status,
    }



def verify_soap_signature_on_vps(signed_xml: str, signer_cert_der: bytes) -> dict:
    """Verify both SignedInfo signature and Body Reference digest via xmlsec1.

    Cryptographic validity proves possession of the corresponding signing
    key, not registration in Smart Bridge, certificate-chain trust or
    revocation status. Caller compares the embedded public certificate with
    the expected SHA-256 fingerprint or public .cer independently.
    """
    # Prefer the provided KalkanCrypt Linux SDK only when explicitly enabled.
    # No .so file is checked into GitHub or loaded into Flask itself.
    if (os.getenv("ISNA_KALKAN_LIBRARY") or "").strip():
        return _verify_with_kalkan(signed_xml)

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
