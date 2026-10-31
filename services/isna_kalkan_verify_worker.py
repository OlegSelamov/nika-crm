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


def verify_native(xml: bytes, library: str) -> bool:
    if not 0 < len(xml) <= MAX_SOAP_BYTES:
        raise ValueError("invalid XML size")
    path = Path(library)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("KalkanCrypt shared library unavailable")
    # ctypes.CDLL is NOT safe to call from the Flask/Gunicorn process; native
    # crashes and hidden SDK global state remain contained in this child.
    api = ctypes.CDLL(str(path))
    init = api.Init
    init.argtypes = []
    init.restype = ctypes.c_ulong
    if init() != 0:
        raise RuntimeError("KalkanCrypt Init failed")

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
        b"", 0, ctypes.cast(data, ctypes.c_void_p), len(xml),
        ctypes.cast(info, ctypes.c_void_p), ctypes.byref(info_len),
    )
    return result == 0


def main() -> int:
    # Return only a fixed-status protocol; no XML, certificate or SDK diagnostic
    # text is printed. Native KalkanCrypt may write its own startup messages.
    status = "error"
    try:
        lib_path = (os.environ.get("ISNA_KALKAN_LIBRARY") or "").strip()
        if not lib_path:
            status = "unavailable"
        else:
            data = sys.stdin.buffer.read(MAX_SOAP_BYTES + 1)
            if len(data) > MAX_SOAP_BYTES:
                status = "error"
            else:
                status = "verified" if verify_native(data, lib_path) else "invalid"
    except (OSError, ValueError):
        status = "unavailable"
    except Exception:
        status = "error"

    sys.stdout.write(PREFIX + json.dumps({"status": status}, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
