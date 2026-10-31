"""Explicit, non-filing routing probe for the real FNO_INTEGRATION TEST service.

Never accepts business payloads, taxpayer information or an inner XMLDSig.
The only permitted requestData/data content is literally '<root/>', which
is not a signed FNO and cannot constitute a tax declaration. A real registered
senderId is used for routing; no sender password or private key is transmitted.

All POSTs are from TEST VPS to the pinned TEST WShEP IP over IPsec.
The signature is made with Android KalkanCrypt (WSSE KeyIdentifier).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
import hashlib
import http.client
import os
import re
import socket
import xml.etree.ElementTree as ET

from scripts.isna_gateway_probe import (
    SOURCE_IP, GATEWAY_IP, GATEWAY_PORT, WSDL_PATH, local_source_available,
)
from scripts.isna_inspect_wss import (
    SOAP, BIP, DS, WSSE, WSU, GOST_SIGNATURE, GOST_DIGEST, EXC_C14N,
    InvalidSoap, extract_signer_certificate, q,
)
from services.isna_bip import (
    IsnaBipError, DEFAULT_TEST_URL, configuration, build_sync_envelope,
)
from services.isna_shep_transport_test import (
    TestGatewayError, _safe_gateway_reply, MAX_REPLY_BYTES,
)

ROUTING_SERVICE = "FNO_INTEGRATION"
ROUTING_DATA = "<root/>"
MAX_PROBE_BYTES = 128000
DATE_WINDOW_SECONDS = 900
FEATURE_FLAG = "ISNA_BIP_ROUTING_PROBE_ENABLED"


def _ensure_test_config():
    if (os.getenv("APP_MODE") or "").strip().lower() != "test":
        raise TestGatewayError("Маршрутизация FNO разрешена только в TEST.")
    if os.getenv(FEATURE_FLAG, "1").strip() != "1":
        raise TestGatewayError("Пробный запрос к FNO_INTEGRATION отключён администратором.")
    cfg = configuration()
    if cfg.endpoint.rstrip("/") != DEFAULT_TEST_URL.rstrip("/"):
        raise TestGatewayError("Адрес должен точно соответствовать TEST ШЭП.")
    if not cfg.sender_id or cfg.sender_id.strip().lower() in ("smartbridge", "nika-offline-test"):
        raise TestGatewayError("Не настроен зарегистрированный senderId ИС Nika.")
    if len(cfg.sender_id) > 128 or any(c.isspace() or c in "<>&'\"" for c in cfg.sender_id):
        raise TestGatewayError("Некорректный senderId TEST системы.")
    return cfg


def draft_real_service_probe():
    """Build exactly one invalid, unsigned FNO business payload; NO network."""
    cfg = _ensure_test_config()
    unsigned = build_sync_envelope(
        ROUTING_DATA,
        service_id=ROUTING_SERVICE,
        sender_id=cfg.sender_id,
        sender_password="",  # no gateway password on the Android device
        data_encoding="string",
    )
    return {
        "soapXml": unsigned,
        "serviceId": ROUTING_SERVICE,
        "realSenderConfigured": True,
        "nonFiling": True,
        "containsTaxpayerData": False,
        "hasSenderPassword": False,
        "gatewayContacted": False,
    }


def _single(parent: ET.Element, tag: str) -> ET.Element:
    parts = list(parent)
    if len(parts) != 1 or parts[0].tag != tag:
        raise InvalidSoap("Unexpected SOAP field layout.")
    return parts[0]


def _require_signature(root: ET.Element, body: ET.Element):
    header = root.find(q(SOAP, "Header"))
    if header is None:
        raise InvalidSoap("SOAP Header required.")
    sec = _single(header, q(WSSE, "Security"))
    sig = _single(sec, q(DS, "Signature"))
    info = sig.find(q(DS, "SignedInfo"))
    if info is None:
        raise InvalidSoap("SOAP SignedInfo missing.")
    body_id = body.get(q(WSU, "Id"))
    if not body_id or not re.fullmatch(r"id-[a-fA-F0-9-]{24,70}", body_id):
        raise InvalidSoap("Unexpected SOAP Body wsu:Id.")
    refs = info.findall(q(DS, "Reference"))
    if len(refs) != 1 or refs[0].get("URI") != "#" + body_id:
        raise InvalidSoap("Signed reference must point exactly to Body.")
    methods = info.findall(q(DS, "SignatureMethod"))
    c14n = info.findall(q(DS, "CanonicalizationMethod"))
    digest = refs[0].find(q(DS, "DigestMethod"))
    transforms = refs[0].find(q(DS, "Transforms"))
    signature_value = sig.find(q(DS, "SignatureValue"))
    digest_value = refs[0].find(q(DS, "DigestValue"))
    if (
        len(methods) != 1 or methods[0].get("Algorithm") != GOST_SIGNATURE
        or len(c14n) != 1 or c14n[0].get("Algorithm") != EXC_C14N
        or digest is None or digest.get("Algorithm") != GOST_DIGEST
        or transforms is None
        or [t.get("Algorithm") for t in transforms.findall(q(DS, "Transform"))] != [EXC_C14N]
        or signature_value is None or not (signature_value.text or "").strip()
        or digest_value is None or not (digest_value.text or "").strip()
    ):
        raise InvalidSoap("Unexpected GOST signed SOAP configuration.")
    if len(root.findall(".//" + q(DS, "Signature"))) != 1:
        raise InvalidSoap("Only one transport XMLDSig is permitted.")
    der, profile = extract_signer_certificate(root)
    if profile != "key-identifier":
        raise InvalidSoap("Routing probe requires the tested KeyIdentifier WS-Security profile.")
    return hashlib.sha256(der).hexdigest().upper()


def validate_real_service_probe(signed_xml: str, *, now: datetime | None = None):
    """Strict structural allowlist. NOT a server-side crypto verification."""
    cfg = _ensure_test_config()
    if not isinstance(signed_xml, str) or not signed_xml or len(signed_xml.encode("utf-8")) > MAX_PROBE_BYTES:
        raise InvalidSoap("Invalid routing probe size.")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", signed_xml, re.IGNORECASE):
        raise InvalidSoap("DTD is forbidden.")
    try:
        root = ET.fromstring(signed_xml.encode("utf-8"))
    except ET.ParseError as exc:
        raise InvalidSoap("Malformed SOAP.") from exc
    if root.tag != q(SOAP, "Envelope") or len(list(root)) != 2:
        raise InvalidSoap("SOAP Envelope expected.")
    body = root.find(q(SOAP, "Body"))
    if body is None:
        raise InvalidSoap("SOAP Body missing.")
    operation = _single(body, q(BIP, "SendMessage"))
    request = _single(operation, "request")
    parts = list(request)
    if len(parts) != 2 or [x.tag for x in parts] != ["requestInfo", "requestData"]:
        raise InvalidSoap("Unexpected service request.")
    info, data_wrapper = parts
    fields = list(info)
    if [f.tag for f in fields] != ["messageId", "serviceId", "messageDate", "sender"]:
        raise InvalidSoap("Missing/extra requestInfo fields.")
    try:
        message_id = str(UUID((fields[0].text or "").strip()))
    except (ValueError, AttributeError):
        raise InvalidSoap("Invalid messageId.") from None
    if fields[1].text != ROUTING_SERVICE:
        raise InvalidSoap("Only FNO_INTEGRATION routing probe is allowed.")
    try:
        stamp = datetime.fromisoformat((fields[2].text or "").replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Timezone missing")
    except ValueError:
        raise InvalidSoap("Invalid SOAP messageDate.") from None
    now = now or datetime.now(timezone.utc)
    if abs((now - stamp.astimezone(timezone.utc)).total_seconds()) > DATE_WINDOW_SECONDS:
        raise InvalidSoap("Routing probe must be signed shortly after generation.")
    sender = _single(fields[3], "senderId")
    if sender.text != cfg.sender_id or sender.attrib:
        raise InvalidSoap("Sender ID must equal configured registered TEST system.")
    data = _single(data_wrapper, "data")
    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    if data.attrib != {q(xsi, "type"): "xs:string"}:
        raise InvalidSoap("Routing data must have xs:string type.")
    if data.text != ROUTING_DATA or list(data) or (data.tail or "").strip():
        raise InvalidSoap("FNO business data are forbidden in routing diagnostics.")
    if data_wrapper.attrib or info.attrib or request.attrib or operation.attrib:
        raise InvalidSoap("Unexpected SOAP metadata attributes.")
    fingerprint = _require_signature(root, body)
    return {
        "structureOk": True,
        "serviceId": ROUTING_SERVICE,
        "senderConfigured": True,
        "nonFiling": True,
        "embeddedCertSha256": fingerprint,
        "certificateProfile": "key-identifier",
        "cryptoVerifiedOnServer": False,
        "messageId": message_id,
    }


def send_real_service_probe(signed_xml: str):
    """Send once to the pinned TEST gateway after Android consent."""
    checked = validate_real_service_probe(signed_xml)
    if not local_source_available():
        raise TestGatewayError("Нет IPsec-адреса на TEST VPS.")
    connection = None
    wire = signed_xml.encode("utf-8")  # NEVER reserialize after Android signs.
    try:
        connection = http.client.HTTPConnection(
            GATEWAY_IP, GATEWAY_PORT, timeout=12,
            source_address=(SOURCE_IP, 0),
        )
        connection.request(
            "POST", WSDL_PATH, body=wire,
            headers={
                "Host": GATEWAY_IP,
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": '""',
                "Accept": "text/xml",
            },
        )
        response = connection.getresponse()
        status = response.status
        raw = response.read(MAX_REPLY_BYTES + 1)
        truncated = len(raw) > MAX_REPLY_BYTES
    except (socket.timeout, OSError, http.client.HTTPException) as exc:
        raise TestGatewayError("TEST ШЭП не ответил через IPsec.") from exc
    finally:
        if connection is not None:
            connection.close()
    parsed = _safe_gateway_reply(raw[:MAX_REPLY_BYTES], truncated)
    return {
        "gatewayContacted": True,
        "httpStatus": status,
        "serviceId": ROUTING_SERVICE,
        "probeKind": "no-signed-business-fno",
        "signedFnoSubmitted": False,
        "taxpayerDataSent": False,
        "businessAccepted": None,
        "gatewayAcceptedSignature": None,
        **parsed,
    }
