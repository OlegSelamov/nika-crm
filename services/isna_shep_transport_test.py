"""A genuine HTTP SOAP POST to the pinned TEST WShEP endpoint.

This intentionally transmits ONLY the strict signed *non-filing* demo from
Nika's TEST server. It never accepts FNO_INTEGRATION or arbitrary service IDs,
does not transmit taxpayer data or credentials, and cannot target production.

The Android device creates and verifies the GOST signature. The server checks
structure (not GOST cryptography); the government gateway is the independent
transport-signature verifier. Its response can be a SOAP Fault: that is not a
successful service authorization or a filed declaration.
"""
from __future__ import annotations

import http.client
import os
import re
import socket
import xml.etree.ElementTree as ET

from scripts.isna_gateway_probe import (
    SOURCE_IP, GATEWAY_IP, GATEWAY_PORT, WSDL_PATH, local_source_available,
)
from scripts.isna_inspect_wss import InvalidSoap, SOAP, q
from services.isna_signed_roundtrip import validate_offline_signed_soap

MAX_REPLY_BYTES = 65536


class TestGatewayError(RuntimeError):
    """Safe-to-expose transport error; never includes raw signed XML."""


def _fault_detail_value(fault: ET.Element, field: str, max_length: int) -> str:
    """Pick only bounded, non-secret diagnostic fields from SOAP Fault detail."""
    for item in fault.iter():
        if item.tag.rsplit("}", 1)[-1] == field:
            value = (item.text or "").strip()
            return re.sub(r"[\\x00-\\x1f\\x7f]", " ", value)[:max_length]
    return ""


def _safe_gateway_reply(payload: bytes, truncated: bool) -> dict:
    result = {"responseType": "unrecognized", "soapFault": False, "replyTruncated": truncated}
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)\b", payload, re.IGNORECASE):
        return result
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return result
    if root.tag != q(SOAP, "Envelope"):
        return result
    body = root.find(q(SOAP, "Body"))
    if body is None:
        return result
    fault = body.find(q(SOAP, "Fault"))
    if fault is not None:
        result["responseType"] = "soap-fault"
        result["soapFault"] = True
        result["faultCode"] = (fault.findtext("faultcode") or "").strip()[:100]
        result["faultMessage"] = (fault.findtext("faultstring") or "").strip()[:350]
        # WShEP often embeds an SCE code and a sessionId inside SOAP Fault/detail.
        # This is more diagnostic than HTTP 500 and helps support investigate
        # a rejected transport signature without sharing private keys or SOAP.
        result["gatewayErrorCode"] = _fault_detail_value(fault, "errorCode", 32)
        result["gatewayErrorDate"] = _fault_detail_value(fault, "errorDate", 80)
        result["gatewaySessionId"] = _fault_detail_value(fault, "sessionId", 120)
    else:
        result["responseType"] = "soap-envelope"
        result["soapFault"] = False
    return result


def send_synthetic_signed_soap(signed_xml: str, *, registered_public_cert=None) -> dict:
    """Make ONE controlled TEST SOAP POST with fixed IP, path and source address."""
    if (os.getenv("APP_MODE") or "").strip().lower() != "test":
        raise TestGatewayError("Функция доступна только в TEST.")
    # Emergency kill switch, fail closed if explicitly disabled.
    if (os.getenv("ISNA_BIP_TEST_POST_ENABLED") or "1").strip() != "1":
        raise TestGatewayError("TEST SOAP POST отключён настройкой сервера.")
    if not local_source_available():
        raise TestGatewayError("TEST VPS не владеет IPsec-адресом. SOAP не отправлен.")
    from services.isna_bip import configuration, DEFAULT_TEST_URL
    if configuration().endpoint.rstrip("/") != DEFAULT_TEST_URL.rstrip("/"):
        raise TestGatewayError("Разрешён только закреплённый адрес TEST ШЭП.")
    try:
        checked = validate_offline_signed_soap(
            signed_xml, registered_public_cert=registered_public_cert,
        )
    except InvalidSoap as exc:
        raise TestGatewayError("Разрешён только подписанный синтетический SOAP Nika.") from exc
    if checked["sampleType"] != "test-server-bip-demo":
        raise TestGatewayError("Запрещено отправлять ФНО или произвольные запросы.")
    if checked["registeredCertMatch"] is False:
        raise TestGatewayError("Публичный сертификат не совпадает с настроенным на TEST VPS.")

    wire = signed_xml.encode("utf-8")  # NEVER parse/re-serialize after signing.
    connection = None
    try:
        connection = http.client.HTTPConnection(
            GATEWAY_IP, GATEWAY_PORT,
            timeout=12, source_address=(SOURCE_IP, 0),
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
        http_status = response.status
        reply = response.read(MAX_REPLY_BYTES + 1)
        truncated = len(reply) > MAX_REPLY_BYTES
        if truncated:
            reply = reply[:MAX_REPLY_BYTES]
    except (socket.timeout, OSError, http.client.HTTPException) as exc:
        raise TestGatewayError(
            "Нет ответа от TEST ШЭП через IPsec. Проверь туннель и журнал VPS."
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    parsed = _safe_gateway_reply(reply, truncated)
    return {
        "gatewayContacted": True,
        "httpStatus": http_status,
        "sampleType": checked["sampleType"],
        "transportSigner": "Android KalkanCrypt",
        "gatewayAcceptedSignature": None,  # SOAP Fault alone is not evidence either way.
        "registeredCertMatch": checked["registeredCertMatch"],
        "filingCreated": False,  # Guaranteed by the non-existent serviceId.
        "noTaxpayerData": True,
        **parsed,
    }
