"""Operator-only, actual FNO_INTEGRATION submission to the PINNED TEST WShEP.

Unlike earlier diagnostic probes this sends a real, separately taxpayer-signed
FNO. It has no HTTP endpoint and deliberately cannot run on production.
There are no embedded keys, test declaration factories, or automatic retries.
Run under a dedicated non-root signing OS account, never www-data.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import getpass
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

from scripts.isna_gateway_probe import (
    SOURCE_IP, GATEWAY_IP, GATEWAY_PORT, WSDL_PATH, local_source_available,
)
from scripts.isna_inspect_wss import extract_signer_certificate
from services.isna_bip import (
    SOAP_NS, BIP_TYPES_NS, WSU_NS, DEFAULT_TEST_URL, configuration,
)
from services.isna_fno_integration import (
    DS_NS, build_fno_integration_soap, inspect_taxpayer_signed_fno,
    parse_fno_integration_response,
)
from services.isna_shep_transport_test import _safe_gateway_reply
from services.isna_transport_certificate import registered_transport_certificate_sha256
from services.isna_transport_signer_cli import (
    _private_key_location, sign_test_soap_native,
)
from services.isna_vps_signature_verifier import (
    verify_inner_fno_signature_on_vps, verify_soap_signature_on_vps,
)

MAX_INNER_BYTES = 120_000  # Native independent verifier has a 256 KB bound.
MAX_SOAP_BYTES = 256_000
MAX_RESPONSE_BYTES = 128_000
SUPPORTED_CODES = frozenset({"200.00", "910.00"})
SEND_CONFIRMATION = "SEND_REAL_FNO_TO_TEST_SHEP"
FLAG = "ISNA_FNO_REAL_TEST_POST_ENABLED"


class FnoSubmissionBlocked(RuntimeError):
    """Safe-to-print message; no P12 password, XML or taxpayer information."""


def _clean_pin(value: str) -> str:
    value = (value or "").strip().replace(":", "").upper()
    if not re.fullmatch(r"[A-F0-9]{64}", value):
        raise FnoSubmissionBlocked("A valid 64-hex SHA-256 confirmation is required.")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _secure_directory(path: Path) -> None:
    if (os.geteuid() == 0 or not path.is_absolute() or path.is_symlink()
            or not path.is_dir() or path.resolve().is_relative_to(Path("/var/www"))):
        raise FnoSubmissionBlocked("Journal directory must be private and outside /var/www.")
    meta = path.stat()
    if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o700:
        raise FnoSubmissionBlocked("Journal directory must be owned by signer and chmod 0700.")


def _private_input(path: Path) -> str:
    if (os.geteuid() == 0 or not path.is_absolute() or path.is_symlink()
            or not path.is_file() or path.resolve().is_relative_to(Path("/var/www"))):
        raise FnoSubmissionBlocked("Taxpayer-signed FNO must be a private absolute file outside /var/www.")
    meta = path.stat()
    if (meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o600
            or not 0 < meta.st_size <= MAX_INNER_BYTES):
        raise FnoSubmissionBlocked("Signed FNO must be owned by signer, chmod 0600, at most 120 KB.")
    try:
        return path.read_bytes().decode("utf-8")
    except (UnicodeError, OSError):
        raise FnoSubmissionBlocked("Signed FNO is unreadable UTF-8.") from None


def _taxpayer_certificate_pin(fno_xml: str) -> str:
    try:
        root = ET.fromstring(fno_xml)
        cert = root.find(
            f"{{{DS_NS}}}Signature/{{{DS_NS}}}KeyInfo/"
            f"{{{DS_NS}}}X509Data/{{{DS_NS}}}X509Certificate"
        )
        if cert is None or not (cert.text or "").strip():
            raise ValueError("X509 certificate missing")
        cert_der = base64.b64decode(re.sub(r"\s+", "", cert.text or ""), validate=True)
        if not 100 <= len(cert_der) <= 65536 or cert_der[0] != 0x30:
            raise ValueError("X509 encoding invalid")
    except (ET.ParseError, ValueError, binascii.Error):
        raise FnoSubmissionBlocked("Taxpayer public X509 certificate missing or invalid.") from None
    return hashlib.sha256(cert_der).hexdigest().upper()


def _test_config():
    if (os.getenv("APP_MODE") or "").strip().lower() != "test":
        raise FnoSubmissionBlocked("A real FNO can be sent only from APP_MODE=test.")
    if (os.getenv(FLAG) or "").strip() != "1":
        raise FnoSubmissionBlocked("Real TEST filing explicitly disabled on the VPS.")
    cfg = configuration()
    if cfg.endpoint.rstrip("/") != DEFAULT_TEST_URL.rstrip("/"):
        raise FnoSubmissionBlocked("Only the pinned TEST WShEP endpoint is allowed.")
    if (not cfg.sender_id or cfg.sender_id.strip().lower() in
            {"smartbridge", "nika-fno-offline-only", "nika-offline-test"}
            or len(cfg.sender_id) > 128 or
            not re.fullmatch(r"[A-Za-z0-9_.@-]+", cfg.sender_id)):
        raise FnoSubmissionBlocked("Verified Nika Smart Bridge senderId is required.")
    registered_pin = registered_transport_certificate_sha256()
    if not registered_pin:
        raise FnoSubmissionBlocked("Expected registered public transport certificate pin is missing.")
    native_library = (os.getenv("ISNA_KALKAN_LIBRARY") or "").strip()
    if not native_library:
        raise FnoSubmissionBlocked("Independent KalkanCrypt verifier library is not configured.")
    if not local_source_available():
        raise FnoSubmissionBlocked("TEST VPS is missing the approved IPsec source address.")
    return cfg, registered_pin, native_library


def _assert_signed_body(signed_soap: str, signed_fno: str, sender: str, message_id: str) -> bytes:
    if (not signed_soap or len(signed_soap.encode("utf-8")) > MAX_SOAP_BYTES or
            re.search(r"<!\s*(DOCTYPE|ENTITY)\b", signed_soap, re.I)):
        raise FnoSubmissionBlocked("Transport-signed SOAP has an invalid size or XML.")
    try:
        root = ET.fromstring(signed_soap)
        if root.tag != f"{{{SOAP_NS}}}Envelope":
            raise ValueError("Envelope")
        body = root.find(f"{{{SOAP_NS}}}Body")
        if body is None or not body.get(f"{{{WSU_NS}}}Id"):
            raise ValueError("Body")
        request = body.find(f"{{{BIP_TYPES_NS}}}SendMessage/request")
        if request is None:
            raise ValueError("SendMessage")
        info = request.find("requestInfo")
        data = request.find("requestData/data")
        if info is None or data is None:
            raise ValueError("Data")
        if (info.findtext("serviceId") != "FNO_INTEGRATION"
                or info.findtext("messageId") != message_id
                or info.findtext("sender/senderId") != sender
                or data.text != signed_fno or len(data) != 0
                or data.get("{http://www.w3.org/2001/XMLSchema-instance}type") != "xs:string"):
            raise ValueError("Unexpected signed business data")
        signer_cert, profile = extract_signer_certificate(root)
        if profile != "key-identifier":
            raise ValueError("WSSE KeyIdentifier required")
        return signer_cert
    except (ET.ParseError, ValueError, TypeError, AttributeError):
        raise FnoSubmissionBlocked("Signer altered the FNO SOAP or used an unsupported WSSE profile.") from None


def _write_journal(path: Path, record: dict, *, first: bool = False) -> None:
    """Persist before POST: a timeout must NEVER lead to an automatic retry."""
    new_path = path if first else path.with_name(path.name + "." + uuid4().hex + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        fd = os.open(new_path, flags, 0o600)
    except FileExistsError:
        raise FnoSubmissionBlocked("This signed FNO already has a submission record. Reconcile status first.") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        if not first:
            os.replace(new_path, path)
    except Exception:
        if not first:
            try:
                new_path.unlink()
            except OSError:
                pass
        raise


def _post_to_test(signed_soap: str) -> tuple[int, bytes, bool]:
    """One POST, exact IP/path/SOAPAction, source-bound to established IPsec."""
    connection = None
    try:
        connection = http.client.HTTPConnection(
            GATEWAY_IP, GATEWAY_PORT, timeout=20,
            source_address=(SOURCE_IP, 0),
        )
        connection.request(
            "POST", WSDL_PATH, body=signed_soap.encode("utf-8"),
            headers={
                "Host": GATEWAY_IP,
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": '""',
                "Accept": "text/xml",
            },
        )
        response = connection.getresponse()
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        return response.status, payload[:MAX_RESPONSE_BYTES], len(payload) > MAX_RESPONSE_BYTES
    except (socket.timeout, OSError, http.client.HTTPException):
        raise FnoSubmissionBlocked(
            "TEST WShEP POST outcome is UNKNOWN (network failure). "
            "Check status and journal before any resubmission."
        ) from None
    finally:
        if connection is not None:
            connection.close()


def _interpret_reply(http_status: int, response: bytes, truncated: bool) -> dict:
    gateway = _safe_gateway_reply(response, truncated)
    report = {
        "httpStatus": http_status,
        "replyTruncated": truncated,
        "gatewayErrorCode": gateway.get("gatewayErrorCode", ""),
        "gatewaySessionId": gateway.get("gatewaySessionId", ""),
        "gatewaySoapFault": gateway.get("soapFault", False),
        "fnoId": None,
        "outcome": "unknown",
    }
    if truncated:
        return report
    try:
        parsed = parse_fno_integration_response(response.decode("utf-8"))
    except (UnicodeError, ValueError, RuntimeError):
        return report
    report["fnoId"] = str(parsed["fno_id"])[:100] if parsed.get("fno_id") else None
    if http_status == 200 and parsed.get("ok") is True:
        report["outcome"] = "service-reported-success"
    elif parsed.get("fault") or parsed.get("service_success") is False:
        report["outcome"] = "rejected"
    return report


def submit_test_fno(args: argparse.Namespace) -> dict:
    if args.confirm != SEND_CONFIRMATION:
        raise FnoSubmissionBlocked("Explicit real TEST submission confirmation is required.")
    if args.expected_code not in SUPPORTED_CODES:
        raise FnoSubmissionBlocked("Only explicitly selected form 200.00 or 910.00 is supported.")
    expected_payload = _clean_pin(args.confirm_payload_sha256)
    expected_taxpayer = _clean_pin(args.taxpayer_cert_sha256)
    _secure_directory(args.journal_dir)
    _private_key_location(args.transport_key)
    cfg, registered_pin, library = _test_config()

    inner_xml = _private_input(args.signed_fno)
    payload_hash = hashlib.sha256(inner_xml.encode("utf-8")).hexdigest().upper()
    if payload_hash != expected_payload:
        raise FnoSubmissionBlocked("Signed FNO does not match the operator-confirmed SHA-256.")
    form = inspect_taxpayer_signed_fno(inner_xml)
    if form["form_code"] != args.expected_code:
        raise FnoSubmissionBlocked("Signed FNO form code is not the expected form.")
    if _taxpayer_certificate_pin(inner_xml) != expected_taxpayer:
        raise FnoSubmissionBlocked("Taxpayer signature certificate is not operator-approved.")

    # Actual GOST signature check, not XMLDSig presence / syntactic parsing.
    verified_inner = verify_inner_fno_signature_on_vps(inner_xml)
    if verified_inner.get("cryptoVerifiedOnServer") is not True:
        raise FnoSubmissionBlocked("Taxpayer XMLDSig failed independent KalkanCrypt verification.")

    message_id = str(uuid4())
    unsigned_soap = build_fno_integration_soap(
        inner_xml, sender_id=cfg.sender_id,
        sender_password=cfg.sender_password, message_id=message_id,
    )
    unsigned_root = ET.fromstring(unsigned_soap)
    body = unsigned_root.find(f"{{{SOAP_NS}}}Body")
    body_id = body.get(f"{{{WSU_NS}}}Id") if body is not None else None
    if not body_id:
        raise FnoSubmissionBlocked("Unsigned SOAP Body ID is unavailable.")

    password = getpass.getpass("Dedicated Nika TEST transport .p12 password: ").encode("utf-8")
    try:
        signed, _, _ = sign_test_soap_native(
            unsigned_soap.encode("utf-8"), library=library,
            key_path=args.transport_key, password=password, body_id=body_id,
        )
    finally:
        del password
    try:
        signed_soap = signed.decode("utf-8")
    except UnicodeError:
        raise FnoSubmissionBlocked("Transport signer output is not UTF-8.") from None
    signer_cert = _assert_signed_body(signed_soap, inner_xml, cfg.sender_id, message_id)
    if hashlib.sha256(signer_cert).hexdigest().upper() != registered_pin:
        raise FnoSubmissionBlocked("Transport signer is not the configured registered public certificate.")
    verified_outer = verify_soap_signature_on_vps(signed_soap, signer_cert)
    if verified_outer.get("cryptoVerifiedOnServer") is not True:
        raise FnoSubmissionBlocked("Transport SOAP Body failed independent KalkanCrypt verification.")

    journal = args.journal_dir / (payload_hash.lower() + ".json")
    record = {
        "version": 1, "createdAt": _now(),
        "payloadSha256": payload_hash, "formCode": args.expected_code,
        "messageId": message_id, "environment": "test",
        "serviceId": "FNO_INTEGRATION", "state": "prepared",
    }
    _write_journal(journal, record, first=True)
    record.update(state="attempted", attemptedAt=_now())
    _write_journal(journal, record)

    # Deliberately no retry. Any timeout/worker exit leaves an attempted record.
    try:
        http_status, response, truncated = _post_to_test(signed_soap)
        parsed = _interpret_reply(http_status, response, truncated)
        record.update(state=parsed["outcome"], completedAt=_now(), reply=parsed)
        _write_journal(journal, record)
    except Exception:
        # Keep attempted journal on disk. A user must explicitly reconcile
        # possible acceptance through FNO_INTEGRATION_STATUS before retrying.
        raise
    return {
        "messageId": message_id, "formCode": args.expected_code,
        "state": parsed["outcome"], "httpStatus": parsed["httpStatus"],
        "gatewayErrorCode": parsed["gatewayErrorCode"],
        "gatewaySessionId": parsed["gatewaySessionId"],
        "fnoId": parsed["fnoId"],
        "journal": str(journal),
        "notice": "A service-reported success is not a final taxpayer acceptance notice.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One REAL signed FNO to pinned TEST WShEP; no production or automatic retry"
    )
    parser.add_argument("--signed-fno", required=True, type=Path)
    parser.add_argument("--transport-key", required=True, type=Path)
    parser.add_argument("--journal-dir", required=True, type=Path)
    parser.add_argument("--expected-code", required=True, choices=sorted(SUPPORTED_CODES))
    parser.add_argument("--confirm-payload-sha256", required=True)
    parser.add_argument("--taxpayer-cert-sha256", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        if (not sys.stdin.isatty() or not sys.stderr.isatty()
                or os.geteuid() == 0 or
                os.geteuid() == __import__("pwd").getpwnam("www-data").pw_uid):
            raise FnoSubmissionBlocked("Use an interactive dedicated signer account (not root or www-data).")
        result = submit_test_fno(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["state"] == "service-reported-success" else 3
    except (FnoSubmissionBlocked, ValueError, OSError) as exc:
        if isinstance(exc, FnoSubmissionBlocked):
            print(f"Real TEST FNO blocked: {exc}", file=sys.stderr)
        else:
            print("Real TEST FNO blocked: invalid input or local configuration.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
