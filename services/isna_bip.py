"""Smart Bridge / BIP transport helpers for ISNA (TEST-first).

This module intentionally does not implement the taxpayer's personal EDS.
It covers the server-to-server Smart Bridge transport layer:
- BIP endpoint/config discovery from environment;
- standard SyncChannel v10 SOAP envelope construction;
- TCP reachability diagnostics from the TEST VPS;
- optional external WS-Security signer command hook;
- POST of an already transport-signed SOAP envelope.

The exact FNO_INTEGRATION payload/XSD mapper is kept separate until the
official service schema/examples are available. This avoids sending a guessed
tax-report format to the government service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import argparse
import os
import shlex
import socket
import subprocess
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4
import xml.etree.ElementTree as ET

import requests


SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
BIP_TYPES_NS = "http://bip.bee.kz/SyncChannel/v10/Types"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
WSU_NS = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-wssecurity-utility-1.0.xsd"
)

DEFAULT_TEST_URL = "http://195.12.113.7/bip-sync-wss-gost/"
DEFAULT_FNO_SERVICE_ID = "FNO_INTEGRATION"
DEFAULT_FNO_STATUS_SERVICE_ID = "FNO_INTEGRATION_STATUS"

ET.register_namespace("soap", SOAP_NS)
ET.register_namespace("typ", BIP_TYPES_NS)
ET.register_namespace("xsi", XSI_NS)
ET.register_namespace("wsu", WSU_NS)


class IsnaBipError(RuntimeError):
    pass


@dataclass(frozen=True)
class IsnaBipConfig:
    endpoint: str
    service_id: str
    status_service_id: str
    sender_id: str
    sender_password: str
    signer_command: str
    timeout_seconds: int
    soap_action: str

    @property
    def sender_ready(self) -> bool:
        return bool(self.sender_id and self.sender_password)

    @property
    def signer_ready(self) -> bool:
        return bool(self.signer_command)


def configuration() -> IsnaBipConfig:
    app_mode = (os.getenv("APP_MODE") or "test").strip().lower()
    default_url = DEFAULT_TEST_URL if app_mode == "test" else ""
    try:
        timeout_seconds = max(3, min(120, int(os.getenv("ISNA_BIP_TIMEOUT", "30"))))
    except ValueError:
        timeout_seconds = 30

    return IsnaBipConfig(
        endpoint=(os.getenv("ISNA_BIP_URL") or default_url).strip(),
        service_id=(os.getenv("ISNA_BIP_SERVICE_ID") or DEFAULT_FNO_SERVICE_ID).strip(),
        status_service_id=(
            os.getenv("ISNA_BIP_STATUS_SERVICE_ID") or DEFAULT_FNO_STATUS_SERVICE_ID
        ).strip(),
        sender_id=(os.getenv("ISNA_BIP_SENDER_ID") or "").strip(),
        sender_password=os.getenv("ISNA_BIP_PASSWORD") or "",
        signer_command=(os.getenv("ISNA_BIP_SIGNER_COMMAND") or "").strip(),
        timeout_seconds=timeout_seconds,
        soap_action=os.getenv("ISNA_BIP_SOAP_ACTION", "").strip(),
    )


def _message_datetime() -> str:
    # Nika Business currently operates in Kazakhstan UTC+5.
    now = datetime.now(timezone(timedelta(hours=5)))
    return now.isoformat(timespec="milliseconds")


def build_sync_envelope(
    data_xml: str,
    *,
    service_id: Optional[str] = None,
    message_id: Optional[str] = None,
    session_id: Optional[str] = None,
    sender_id: Optional[str] = None,
    sender_password: Optional[str] = None,
) -> str:
    """Build an unsigned BIP SyncChannel v10 SOAP envelope.

    data_xml must be the *official service request element* for the selected
    Smart Bridge service. We deliberately do not invent the FNO_INTEGRATION
    XSD payload here.
    """
    cfg = configuration()
    service_id = (service_id or cfg.service_id).strip()
    sender_id = cfg.sender_id if sender_id is None else sender_id
    sender_password = cfg.sender_password if sender_password is None else sender_password

    if not service_id:
        raise IsnaBipError("Smart Bridge serviceId is empty.")
    if not sender_id:
        raise IsnaBipError(
            "Smart Bridge sender ID is not configured (ISNA_BIP_SENDER_ID)."
        )

    try:
        data_node = ET.fromstring(data_xml)
    except ET.ParseError as exc:
        raise IsnaBipError(f"Invalid service payload XML: {exc}") from exc

    message_id = message_id or str(uuid4())

    envelope = ET.Element(ET.QName(SOAP_NS, "Envelope"))
    header = ET.SubElement(envelope, ET.QName(SOAP_NS, "Header"))
    # The WS-Security signer will populate the header later.
    header.set(ET.QName(SOAP_NS, "mustUnderstand"), "0")

    body = ET.SubElement(envelope, ET.QName(SOAP_NS, "Body"))
    body.set(ET.QName(WSU_NS, "Id"), "id-" + str(uuid4()))

    send_message = ET.SubElement(body, ET.QName(BIP_TYPES_NS, "SendMessage"))
    request = ET.SubElement(send_message, "request")
    request_info = ET.SubElement(request, "requestInfo")

    ET.SubElement(request_info, "messageId").text = message_id
    ET.SubElement(request_info, "serviceId").text = service_id
    ET.SubElement(request_info, "messageDate").text = _message_datetime()

    sender = ET.SubElement(request_info, "sender")
    ET.SubElement(sender, "senderId").text = sender_id
    if sender_password:
        ET.SubElement(sender, "password").text = sender_password
    # sessionId is assigned by BIP; do not fabricate it in client requests.
    if session_id:
        ET.SubElement(request_info, "sessionId").text = session_id

    request_data = ET.SubElement(request, "requestData")
    # SyncChannel v10 schema requires requestData/data (xsd:anyType).
    ET.SubElement(request_data, "data").append(data_node)

    return ET.tostring(envelope, encoding="unicode", xml_declaration=False)


def sign_transport_envelope(unsigned_xml: str) -> str:
    """Sign SOAP via an external official/approved WS-Security signer.

    ISNA_BIP_SIGNER_COMMAND is intentionally external so that KalkanCrypt/Java
    tooling and the transport certificate remain outside the Python web app.
    The command reads unsigned XML from stdin and must write signed XML to stdout.
    """
    cfg = configuration()
    if not cfg.signer_command:
        raise IsnaBipError(
            "Transport signer is not configured (ISNA_BIP_SIGNER_COMMAND)."
        )

    try:
        result = subprocess.run(
            shlex.split(cfg.signer_command),
            input=unsigned_xml,
            text=True,
            capture_output=True,
            timeout=cfg.timeout_seconds,
            check=False,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IsnaBipError(f"Transport signer failed to start: {exc}") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise IsnaBipError(
            f"Transport signer returned code {result.returncode}: "
            f"{stderr[:500] or 'no diagnostic output'}"
        )

    signed_xml = (result.stdout or "").strip()
    if "<" not in signed_xml or "Signature" not in signed_xml:
        raise IsnaBipError("Transport signer returned no WS-Security signature.")
    return signed_xml


def post_signed_envelope(signed_xml: str) -> requests.Response:
    cfg = configuration()
    if not cfg.endpoint:
        raise IsnaBipError("ISNA_BIP_URL is not configured.")
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
    }
    # The supplied SyncChannel v10 WSDL declares soapAction="".
    headers["SOAPAction"] = cfg.soap_action

    try:
        return requests.post(
            cfg.endpoint,
            data=signed_xml.encode("utf-8"),
            headers=headers,
            timeout=cfg.timeout_seconds,
        )
    except requests.RequestException as exc:
        raise IsnaBipError(f"BIP request failed: {exc}") from exc


def probe_tcp() -> dict:
    """Check network reachability only; sends no SOAP/tax request."""
    cfg = configuration()
    if not cfg.endpoint:
        return {
            "ok": False,
            "endpoint": "",
            "error": "ISNA_BIP_URL is not configured.",
        }

    parsed = urlparse(cfg.endpoint)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        return {
            "ok": False,
            "endpoint": cfg.endpoint,
            "error": "Invalid BIP endpoint.",
        }

    try:
        with socket.create_connection((host, port), timeout=min(cfg.timeout_seconds, 10)):
            pass
        return {
            "ok": True,
            "endpoint": cfg.endpoint,
            "host": host,
            "port": port,
            "service_id": cfg.service_id,
            "status_service_id": cfg.status_service_id,
            "sender_configured": cfg.sender_ready,
            "transport_signer_configured": cfg.signer_ready,
        }
    except OSError as exc:
        return {
            "ok": False,
            "endpoint": cfg.endpoint,
            "host": host,
            "port": port,
            "error": str(exc),
            "sender_configured": cfg.sender_ready,
            "transport_signer_configured": cfg.signer_ready,
        }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Nika ISNA / Smart Bridge diagnostics")
    parser.add_argument("--probe", action="store_true", help="TCP reachability check")
    parser.add_argument("--check-config", action="store_true", help="Report safe configuration readiness (no credentials printed)")
    parser.add_argument("--prepare-unsigned", metavar="OFFICIAL_PAYLOAD_XML", help="Build an unsigned SOAP envelope locally, without sending")
    parser.add_argument("--output", metavar="SOAP_XML", help="Output file for --prepare-unsigned (created with mode 0600)")
    args = parser.parse_args()

    if args.check_config or args.prepare_unsigned:
        # Read test-specific environment without printing credentials or key material.
        from dotenv import load_dotenv
        load_dotenv(override=False)
        cfg = configuration()
        app_mode = (os.getenv("APP_MODE") or "test").strip().lower()
        if args.check_config:
            print("Environment:", app_mode)
            print("Endpoint:", cfg.endpoint or "NOT SET")
            print("Sender ID:", "configured" if cfg.sender_id else "MISSING")
            print("Sender password:", "configured" if cfg.sender_password else "not configured (optional in WSDL)")
            print("Transport signer:", "configured" if cfg.signer_ready else "MISSING")
            print("Service ID:", cfg.service_id, "(default, not verified)" if not os.getenv("ISNA_BIP_SERVICE_ID") else "(configured)")
            print("SOAPAction:", repr(cfg.soap_action))
            print("OFFLINE CHECK ONLY: no request was sent.")
            return 0
        if app_mode != "test":
            parser.error("--prepare-unsigned is limited to APP_MODE=test")
        if not args.output:
            parser.error("--output is required with --prepare-unsigned")
        from pathlib import Path
        payload_xml = Path(args.prepare_unsigned).read_text(encoding="utf-8")
        unsigned_xml = build_sync_envelope(payload_xml)
        # XML can contain service data and sender credentials. Never dump to stdout;
        # write only to a new private file and refuse to overwrite existing files.
        fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(unsigned_xml)
        print("Unsigned SOAP envelope saved privately to:", args.output)
        print("NOT SENT. Must be transport-signed; verify official service XSD/IDs first.")
        return 0

    if args.probe:
        result = probe_tcp()
        print(
            "BIP TCP probe:",
            "OK" if result.get("ok") else "FAILED",
            f"{result.get('host', '')}:{result.get('port', '')}",
        )
        print("endpoint:", result.get("endpoint") or "-")
        print("service:", result.get("service_id") or DEFAULT_FNO_SERVICE_ID)
        print(
            "sender configured:",
            "yes" if result.get("sender_configured") else "no",
        )
        print(
            "transport signer configured:",
            "yes" if result.get("transport_signer_configured") else "no",
        )
        if result.get("error"):
            print("error:", result["error"])
        return 0 if result.get("ok") else 2

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
