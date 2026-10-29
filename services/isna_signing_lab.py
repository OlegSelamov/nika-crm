"""Nika ISNA: non-filing server-to-Android signing handshake (TEST only).

The payload intentionally uses a NON-EXISTENT serviceId, synthetic senderId,
no sender password and no taxpayer data. Do not POST it to Smart Bridge.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from services.isna_bip import build_sync_envelope, SOAP_NS, BIP_TYPES_NS, WSU_NS, IsnaBipError

OFFLINE_SERVICE_ID = "NIKA_ISNA_OFFLINE_SIGNING_ONLY"
OFFLINE_SENDER_ID = "nika-offline-test"
DEMO_NS = "urn:nikabusiness:offline-soap-test:1"


def create_server_signing_sample() -> dict:
    """Build unsigned BIP-like SOAP for an Android local-signing experiment."""
    payload = (
        '<test:NikaWsSecurityTest xmlns:test="urn:nikabusiness:offline-soap-test:1">'
        '<test:Submission>false</test:Submission>'
        '<test:Purpose>Server-to-Android offline signature test only</test:Purpose>'
        '</test:NikaWsSecurityTest>'
    )
    xml = build_sync_envelope(
        payload,
        service_id=OFFLINE_SERVICE_ID,
        sender_id=OFFLINE_SENDER_ID,
        sender_password="",  # NEVER put actual Smart Bridge credentials in mobile demo.
        data_encoding="xml",
    )
    # The test contract explicitly prohibits accidental production service IDs.
    root = ET.fromstring(xml)
    body = root.find(f"{{{SOAP_NS}}}Body")
    if body is None or not body.get(f"{{{WSU_NS}}}Id"):
        raise IsnaBipError("Offline SOAP sample missing signed body reference.")
    info = root.find(
        f".//{{{BIP_TYPES_NS}}}SendMessage/request/requestInfo"
    )
    if info is None or info.findtext("serviceId") != OFFLINE_SERVICE_ID:
        raise IsnaBipError("Offline SOAP sample has unexpected serviceId.")
    return {
        "soapXml": xml,
        "offlineOnly": True,
        "soapSent": False,
        "hasTaxpayerData": False,
        "hasGatewayPassword": False,
    }
