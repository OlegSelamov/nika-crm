"""Isolated KalkanCrypt XMLDSig verifier process for synthetic ISNA TEST SOAP.

This process intentionally loads native code OUTSIDE Gunicorn. A crash, hang or
global crypto-provider mutation must not bring down the Flask workers. The
parent validates the exact inert SOAP structure and certificate pin before
invoking this worker. No private key or password is used.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import sys

PREFIX = "NIKA_KALKAN_XML_VERIFY_V1:"
MAX_SOAP_BYTES = 256_000
MAX_REPORT = 8192
# SDK KalkanCrypt.h: KC_XML_EXCL_C14N. Android uses exclusive XML C14N
# for both SignedInfo and its single SOAP Body Reference transform.
KC_XML_EXCL_C14N = 0x01000010
# Official KalkanCrypt.h: certificate role values.
KC_CERT_CA = 0x00000201
KC_CERT_INTERMEDIATE = 0x00000202


class KalkanTrustError(RuntimeError):
    def __init__(self, native_code: int):
        self.native_code = f'0x{int(native_code):08X}'
        super().__init__('KalkanCrypt trust load failed')


def load_test_trust(api: ctypes.CDLL, directory: str) -> None:
    # Load only the two pinned 2022 GOST CA files in this verifier process.
    # This must NEVER add a new OS-wide trust anchor or use a private key.
    if not directory:
        return
    root = Path(directory)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ValueError('KalkanCrypt TEST trust directory unavailable')
    load = api.X509LoadCertificateFromFile
    load.argtypes = [ctypes.c_char_p, ctypes.c_int]
    load.restype = ctypes.c_ulong
    for filename, cert_type in (
        ('root_gost_2022.pem', KC_CERT_CA),
        ('nca_gost_2022.pem', KC_CERT_INTERMEDIATE),
    ):
        file = root / filename
        if not file.is_file() or file.is_symlink() or file.stat().st_size > 32768:
            raise ValueError('Required KalkanCrypt TEST CA missing')
        code = load(os.fsencode(file), cert_type)
        if code != 0:
            raise KalkanTrustError(code)



def verify_native(xml: bytes, library: str) -> tuple[bool, str]:
    if not 0 < len(xml) <= MAX_SOAP_BYTES:
        raise ValueError("invalid XML size")
    path = Path(library)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("KalkanCrypt shared library unavailable")
    # ctypes.CDLL is NOT safe to call from the Flask/Gunicorn process; native
    # crashes and hidden SDK global state remain contained in this child.
    # SDK 2.0.14 exports unresolved legacy SRP_Calc_A references, which
    # prevent RTLD_NOW loading even when VerifyXML/Init work. The NCA RK
    # forum recommends RTLD_LAZY. Keep this inside the disposable subprocess:
    # if a missing symbol is actually called, the child fails closed.
    api = ctypes.CDLL(str(path), mode=os.RTLD_LAZY)
    init = api.Init
    init.argtypes = []
    init.restype = ctypes.c_ulong
    if init() != 0:
        raise RuntimeError("KalkanCrypt Init failed")
    load_test_trust(api, (os.getenv('ISNA_KALKAN_CA_DIR') or '').strip())

    # Linux x86-64 KalkanCrypt SDK 2.0.14 C ABI:
    # VerifyXML(alias, flags, xml, xmlLen, verifyInfo, verifyInfoLen*)
    verify = api.VerifyXML
    verify.argtypes = [
        ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
    ]
    verify.restype = ctypes.c_ulong
    data = ctypes.create_string_buffer(xml, len(xml) + 1)
    info = ctypes.create_string_buffer(MAX_REPORT)
    info_len = ctypes.c_int(MAX_REPORT)
    # No key store is loaded. Public signer certificate is embedded in SOAP.
    result = verify(
        b"", KC_XML_EXCL_C14N, ctypes.cast(data, ctypes.c_void_p), len(xml),
        ctypes.cast(info, ctypes.c_void_p), ctypes.byref(info_len),
    )
    # Status only. Do not expose native verifyInfo: it may include parts of the
    # untrusted SOAP or certificate. Include the numerical return code to
    # distinguish unsigned XML, invalid digest, unsupported IDs and flags.
    return result == 0, f"0x{int(result):08X}"


def main() -> int:
    # Return only a fixed-status protocol; no XML, certificate or SDK diagnostic
    # text is printed. Native KalkanCrypt may write its own startup messages.
    status = "error"
    native_code = None
    try:
        lib_path = (os.environ.get("ISNA_KALKAN_LIBRARY") or "").strip()
        if not lib_path:
            status = "unavailable"
        else:
            data = sys.stdin.buffer.read(MAX_SOAP_BYTES + 1)
            if len(data) > MAX_SOAP_BYTES:
                status = "error"
            else:
                valid, native_code = verify_native(data, lib_path)
                status = "verified" if valid else "invalid"
    except KalkanTrustError as exc:
        status = "error"
        native_code = exc.native_code
    except (OSError, ValueError):
        status = "unavailable"
    except Exception:
        status = "error"

    payload = {"status": status}
    if native_code is not None:
        payload["code"] = native_code
    sys.stdout.write(PREFIX + json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
