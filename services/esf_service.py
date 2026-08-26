"""SOAP client for the Kazakhstan IS ESF API.

The private key never reaches this module. XML and CMS signatures are produced
in the user's browser by NCALayer; the server only forwards signed values to
the official IS ESF web services.
"""

from dataclasses import dataclass
import os
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import requests


SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
ESF_NS = "esf"
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
PASSWORD_TEXT = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-username-token-profile-1.0#PasswordText"
)

API_BASES = {
    "test": "https://test3.esf.kgd.gov.kz:8443/esf-web/ws/api1",
    "production": "https://esf.gov.kz:8443/esf-web/ws/api1",
}


class EsfApiError(RuntimeError):
    """A safe, user-facing error returned by IS ESF or its transport."""

    def __init__(self, message, *, details=None, status_code=None):
        super().__init__(message)
        self.details = details or []
        self.status_code = status_code


@dataclass(frozen=True)
class EsfApiConfig:
    environment: str
    base_url: str
    timeout: int
    verify_tls: bool


def configuration():
    environment = str(os.getenv("ESF_API_ENV", "production")).strip().lower()
    if environment in {"prod", "production", "live"}:
        environment = "production"
    else:
        environment = "test"

    configured_url = str(os.getenv("ESF_API_BASE_URL", "")).strip().rstrip("/")
    base_url = configured_url or API_BASES[environment]
    try:
        timeout = max(10, min(int(os.getenv("ESF_API_TIMEOUT", "60")), 180))
    except (TypeError, ValueError):
        timeout = 60
    verify_tls = str(os.getenv("ESF_API_VERIFY_TLS", "true")).strip().lower() not in {
        "0", "false", "no", "off"
    }
    return EsfApiConfig(environment, base_url, timeout, verify_tls)


def _tag(namespace, name):
    return f"{{{namespace}}}{name}"


def _local_name(tag):
    return str(tag).rsplit("}", 1)[-1]


def _first_text(root, name):
    for element in root.iter():
        if _local_name(element.tag) == name and element.text:
            return element.text.strip()
    return ""


def _children_named(root, name):
    return [element for element in root.iter() if _local_name(element.tag) == name]


def _direct_child_text(root, name):
    for element in list(root):
        if _local_name(element.tag) == name:
            return str(element.text or "").strip()
    return ""


def _add(parent, name, value, namespace=None):
    child = ET.SubElement(parent, _tag(namespace, name) if namespace else name)
    child.text = str(value or "")
    return child


def _certificate_body(value):
    text = str(value or "").strip()
    text = re.sub(r"-----BEGIN CERTIFICATE-----|-----END CERTIFICATE-----", "", text)
    return re.sub(r"\s+", "", text)


def _soap_envelope(request_element, *, username=None, password=None):
    ET.register_namespace("soapenv", SOAP_NS)
    ET.register_namespace("esf", ESF_NS)
    ET.register_namespace("wsse", WSSE_NS)
    ET.register_namespace("wsu", WSU_NS)
    envelope = ET.Element(_tag(SOAP_NS, "Envelope"))
    header = ET.SubElement(envelope, _tag(SOAP_NS, "Header"))
    if username or password:
        security = ET.SubElement(header, _tag(WSSE_NS, "Security"))
        security.set(_tag(SOAP_NS, "mustUnderstand"), "1")
        token = ET.SubElement(security, _tag(WSSE_NS, "UsernameToken"))
        token.set(_tag(WSU_NS, "Id"), "NikaEsfUsernameToken")
        _add(token, "Username", username, WSSE_NS)
        password_element = _add(token, "Password", password, WSSE_NS)
        password_element.set("Type", PASSWORD_TEXT)
    body = ET.SubElement(envelope, _tag(SOAP_NS, "Body"))
    body.append(request_element)
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def _fault_details(root):
    details = []
    for error in _children_named(root, "error"):
        code = _direct_child_text(error, "errorCode") or _direct_child_text(error, "code")
        text = _direct_child_text(error, "text") or _direct_child_text(error, "message")
        property_name = _direct_child_text(error, "property")
        message = ": ".join(part for part in (property_name, text or code) if part)
        if message and message not in details:
            details.append(message)
    return details


def _soap_call(service, request_element, *, username=None, password=None):
    config = configuration()
    payload = _soap_envelope(request_element, username=username, password=password)
    try:
        response = requests.post(
            f"{config.base_url}/{service}",
            data=payload,
            headers={"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": ""},
            timeout=config.timeout,
            verify=config.verify_tls,
        )
    except requests.Timeout as exc:
        raise EsfApiError("ИС ЭСФ не ответила вовремя. Повторите попытку.") from exc
    except requests.RequestException as exc:
        raise EsfApiError(f"Не удалось подключиться к ИС ЭСФ: {exc}") from exc

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise EsfApiError(
            f"ИС ЭСФ вернула ответ в неизвестном формате (HTTP {response.status_code}).",
            status_code=response.status_code,
        ) from exc

    fault = next((item for item in root.iter() if _local_name(item.tag) == "Fault"), None)
    if fault is not None or response.status_code >= 400:
        fault_root = fault if fault is not None else root
        message = _first_text(fault_root, "faultstring")
        if not message:
            message = _first_text(fault_root, "message") or _first_text(fault_root, "reason")
        details = _fault_details(fault_root)
        raise EsfApiError(
            message or f"ИС ЭСФ отклонила запрос (HTTP {response.status_code}).",
            details=details,
            status_code=response.status_code,
        )
    return root


def create_auth_ticket(iin, ttl_minutes=15):
    request_element = ET.Element(_tag(ESF_NS, "createAuthTicketRequest"))
    _add(request_element, "iin", iin)
    _add(request_element, "ttlInMinutes", ttl_minutes)
    root = _soap_call("AuthService", request_element)
    ticket = _first_text(root, "authTicketXml")
    if not ticket:
        raise EsfApiError("ИС ЭСФ не вернула тикет авторизации.")
    return ticket


def create_signed_session(*, tin, iin, password, signed_auth_ticket, profile_type=None):
    request_element = ET.Element(_tag(ESF_NS, "createSessionSignedRequest"))
    _add(request_element, "tin", tin)
    if profile_type:
        _add(request_element, "businessProfileType", profile_type)
    _add(request_element, "signedAuthTicket", signed_auth_ticket)
    _add(request_element, "sourceType", "OTHER")
    root = _soap_call(
        "SessionService",
        request_element,
        username=iin,
        password=password,
    )
    session_id = _first_text(root, "sessionId")
    if not session_id:
        raise EsfApiError("ИС ЭСФ не открыла API-сессию.")
    return session_id


def close_session(session_id, *, iin=None, password=None):
    if not session_id:
        return
    request_element = ET.Element(_tag(ESF_NS, "closeSessionRequest"))
    _add(request_element, "sessionId", session_id)
    try:
        _soap_call("SessionService", request_element, username=iin, password=password)
    except EsfApiError:
        # A failed close must not hide the result of the business operation.
        pass


def send_invoice(*, session_id, invoice_xml, signature, certificate, version="InvoiceV2"):
    request_element = ET.Element(_tag(ESF_NS, "syncInvoiceRequest"))
    _add(request_element, "sessionId", session_id)
    upload_list = ET.SubElement(request_element, "invoiceUploadInfoList")
    upload = ET.SubElement(upload_list, "invoiceUploadInfo")
    _add(upload, "invoiceBody", invoice_xml)
    _add(upload, "version", version)
    _add(upload, "signature", signature)
    _add(upload, "signatureType", "COMPANY")
    _add(request_element, "x509Certificate", _certificate_body(certificate))
    root = _soap_call("UploadInvoiceService", request_element)

    accepted = []
    declined = []
    for group in root.iter():
        group_name = _local_name(group.tag)
        if group_name not in {"acceptedSet", "declinedSet"}:
            continue
        target = accepted if group_name == "acceptedSet" else declined
        for result in list(group):
            if _local_name(result.tag) != "standardResponse":
                continue
            target.append({
                "id": _direct_child_text(result, "id"),
                "num": _direct_child_text(result, "num"),
                "date": _direct_child_text(result, "date"),
                "errors": _fault_details(result),
            })
    if declined or not accepted:
        details = []
        for item in declined:
            details.extend(item.get("errors") or [])
        raise EsfApiError("ИС ЭСФ отклонила электронный счёт-фактуру.", details=details)
    return accepted[0]


def build_revoke_signable(invoice_id, reason):
    invoice_id = str(int(invoice_id))
    reason = str(reason or "").strip()
    return (
        "<signedContent><idsWithReasons><idWithReason>"
        f"<id>{invoice_id}</id><reason>{escape(reason)}</reason>"
        "</idWithReason></idsWithReasons></signedContent>"
    )


def revoke_invoice(*, session_id, invoice_id, reason, signature, certificate):
    request_element = ET.Element(_tag(ESF_NS, "revokeInvoiceByIdRequest"))
    _add(request_element, "sessionId", session_id)
    _add(request_element, "signature", signature)
    _add(request_element, "x509Certificate", _certificate_body(certificate))
    reason_list = ET.SubElement(request_element, "idWithReasonList")
    invoice_reason = ET.SubElement(reason_list, "invoiceIdWithReason")
    _add(invoice_reason, "id", invoice_id)
    _add(invoice_reason, "reason", reason)
    root = _soap_call("InvoiceService", request_element)

    result = next((item for item in root.iter() if _local_name(item.tag) == "changeStatusResult"), None)
    if result is None:
        raise EsfApiError("ИС ЭСФ не вернула результат отзыва.")
    changed = _first_text(result, "isChanged").lower() == "true"
    status = _first_text(result, "invoiceStatus")
    details = _fault_details(result)
    direct_error = _first_text(result, "errorText") or _first_text(result, "errorCode")
    if direct_error and direct_error not in details:
        details.append(direct_error)
    if not changed and status not in {"REVOKED", "WAITING_CUSTOMER_REVOKE_CONFIRMATION"}:
        raise EsfApiError("ИС ЭСФ не выполнила отзыв.", details=details)
    return {
        "changed": changed,
        "status": status,
        "registration_number": _first_text(result, "registrationNumber"),
        "reason": _first_text(result, "cancelReason") or reason,
        "details": details,
    }
