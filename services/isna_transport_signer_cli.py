"""ISNA TEST only: operator-run KalkanCrypt WSSE signing experiment.

Uses SDK 2.0.14 native SignWSSE with a dedicated *system* PKCS#12.
Deliberately generates ONLY the hard-coded non-filing SOAP sample.
Never accepts client-supplied XML, contacts ŠEP, or exposes an HTTP route.

Private .p12 must belong to a separate unprivileged OS signer account and
must not be readable by Gunicorn/www-data. Password is read from a TTY,
not CLI arguments, environment variables or a Flask request.
"""
from __future__ import annotations

import argparse
import ctypes
import getpass
import os
from pathlib import Path
import stat
import sys

from services.isna_kalkan_verify_worker import KC_XML_EXCL_C14N
from services.isna_signed_roundtrip import validate_offline_signed_soap
from services.isna_signing_lab import create_server_signing_sample
from services.isna_transport_certificate import registered_transport_certificate_sha256

KCST_PKCS12 = 0x00000001
MAX_TEST_BYTES = 256_000
MAX_SIGNED_BYTES = 384_000


class SigningUnavailable(RuntimeError):
    """Safe-to-display reason, never includes a PIN, key bytes or SDK output."""


def _private_key_location(path: Path) -> None:
    if not path.is_absolute() or path.suffix.lower() not in (".p12", ".pfx"):
        raise SigningUnavailable("A private absolute .p12/.pfx path is required.")
    if path.is_symlink() or not path.is_file():
        raise SigningUnavailable("Transport PKCS12 is not an ordinary file.")
    if path.resolve().is_relative_to(Path("/var/www")):
        raise SigningUnavailable("Transport PKCS12 cannot live in a web-served tree.")
    mode = path.stat()
    if (mode.st_uid != os.geteuid() or stat.S_IMODE(mode.st_mode) != 0o600
            or not 0 < mode.st_size < 512_000):
        raise SigningUnavailable("PKCS12 must be owned by the signer account, chmod 0600.")
    if os.geteuid() == 0:
        raise SigningUnavailable("Refusing root: use a separate unprivileged signer account.")


def sign_test_soap_native(soap: bytes, *, library: str, key_path: Path, password: bytes,
                          body_id: str) -> tuple[bytes, str, str]:
    """Native C ABI: KC_LoadKeyStore then SignWSSE; failure always blocks output.

    Returns (signed XML, load_status, sign_status). This function is never
    called from web workers; the main routine requires an interactive TTY.
    """
    if not 0 < len(soap) <= MAX_TEST_BYTES:
        raise SigningUnavailable("Test SOAP exceeds bounded size.")
    if not body_id.startswith("id-") or len(body_id) > 100:
        raise SigningUnavailable("Invalid SOAP Body ID.")
    lib = Path(library)
    if not lib.is_absolute() or lib.is_symlink() or not lib.is_file():
        raise SigningUnavailable("KalkanCrypt library is not available.")
    _private_key_location(key_path)
    if not password or len(password) > 1024:
        raise SigningUnavailable("Empty/oversized interactive password.")

    # SDK 2.0.14 needs RTLD_LAZY on this TEST Linux VPS.
    api = ctypes.CDLL(str(lib), mode=os.RTLD_LAZY)
    api.Init.argtypes = []
    api.Init.restype = ctypes.c_ulong
    code = api.Init()
    if code:
        raise SigningUnavailable(f"KalkanCrypt Init failed: 0x{code:08X}")
    try:
        load = api.KC_LoadKeyStore
        load.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                         ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
        load.restype = ctypes.c_ulong
        alias = ctypes.create_string_buffer(256)
        password_buffer = ctypes.create_string_buffer(password)
        path_bytes = os.fsencode(key_path)
        code = load(KCST_PKCS12, ctypes.cast(password_buffer, ctypes.c_char_p), len(password),
                    path_bytes, len(path_bytes), ctypes.cast(alias, ctypes.c_char_p))
        # Best-effort clearing of our mutable copy; the caller's password
        # bytes and the native provider's internal copies are process-scoped.
        ctypes.memset(password_buffer, 0, ctypes.sizeof(password_buffer))
        if code:
            raise SigningUnavailable(f"KalkanCrypt keystore load rejected: 0x{code:08X}")

        native_sign = api.SignWSSE
        native_sign.argtypes = (ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p,
                                ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                ctypes.c_char_p)
        native_sign.restype = ctypes.c_ulong
        capacity = min(MAX_SIGNED_BYTES, len(soap) + 65536)
        out = ctypes.create_string_buffer(capacity)
        size = ctypes.c_int(capacity)
        code = native_sign(ctypes.cast(alias, ctypes.c_char_p), KC_XML_EXCL_C14N,
                           soap, len(soap), out, ctypes.byref(size),
                           body_id.encode("ascii"))
        if code:
            raise SigningUnavailable(f"KalkanCrypt SignWSSE rejected: 0x{code:08X}")
        if not 0 < size.value <= capacity:
            raise SigningUnavailable("KalkanCrypt returned an invalid output length.")
        signed = out.raw[:size.value].rstrip(b"\x00")
        if not signed.startswith(b"<") and not signed.startswith(b"<?xml"):
            raise SigningUnavailable("KalkanCrypt did not return signed XML.")
        return signed, "0x00000000", "0x00000000"
    finally:
        try:
            api.KC_XMLFinalize()
            api.KC_Finalize()
        except (AttributeError, OSError):
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="One-off non-filing ISNA TEST transport signing; no gateway POST")
    parser.add_argument("--key-file", required=True, type=Path, help="Private transport P12; NEVER send to GitHub")
    parser.add_argument("--output", required=True, type=Path, help="Private output XML path, must not exist")
    args = parser.parse_args()
    try:
        if (os.getenv("APP_MODE") or "").strip().lower() != "test":
            raise SigningUnavailable("Signing experiment runs only in APP_MODE=test.")
        if not os.isatty(sys.stdin.fileno()) or not os.isatty(sys.stderr.fileno()):
            raise SigningUnavailable("Interactive console required (password not accepted over pipes).")
        pin = registered_transport_certificate_sha256()
        if not pin:
            raise SigningUnavailable("Registered transport PUBLIC cert SHA-256/path must be configured first.")
        lib = (os.getenv("ISNA_KALKAN_LIBRARY") or "").strip()
        _private_key_location(args.key_file)
        if not args.output.is_absolute() or args.output.resolve().is_relative_to(Path("/var/www")):
            raise SigningUnavailable("Signed offline XML must be written outside /var/www.")
        if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
            raise SigningUnavailable("Output file already exists or parent directory is invalid.")
        from services.isna_bip import SOAP_NS, WSU_NS
        import xml.etree.ElementTree as ET
        soap = create_server_signing_sample()["soapXml"]
        root = ET.fromstring(soap)
        body = root.find(f"{{{SOAP_NS}}}Body")
        if body is None:
            raise SigningUnavailable("Missing SOAP Body.")
        body_id = body.get(f"{{{WSU_NS}}}Id") or ""
        passphrase = getpass.getpass("Dedicated TEST transport .p12 password: ").encode("utf-8")
        signed, _, _ = sign_test_soap_native(soap.encode("utf-8"), library=lib,
                                             key_path=args.key_file, password=passphrase,
                                             body_id=body_id)
        # Independent GOST verification in a separate child KalkanCrypt
        # process, plus exact non-filing SOAP structure/profile allowlist.
        report = validate_offline_signed_soap(signed.decode("utf-8"))
        if not report.get("cryptoVerifiedOnServer"):
            raise SigningUnavailable(
                "Signed SOAP did not pass independent XMLDSig check: "
                + str(report.get("cryptoNativeCode") or report.get("cryptoVerificationStatus"))
            )
        if report.get("embeddedCertSha256") != pin:
            raise SigningUnavailable("Signer does not match the registered public transport certificate PIN.")
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(signed)
        print("OFFLINE TEST: WSSE signature independently verified on local KalkanCrypt worker.")
        print("Transport certificate matches configured PUBLIC SHA-256. No gateway POST.")
        print("Signed non-filing XML saved with mode 0600.")
        return 0
    except (SigningUnavailable, ValueError, OSError) as exc:
        # Explicitly never print raw XML, SDK error strings, passwords or key paths.
        print(f"TEST-only signing blocked: {exc if isinstance(exc, SigningUnavailable) else 'invalid input or configuration'}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
