from flask import Blueprint, request, jsonify, session
from datetime import datetime
import requests
import os
import uuid
import json
import re
import threading
import time
from urllib.parse import urlsplit

rekassa_bp = Blueprint("rekassa", __name__)

REKASSA_API_KEY = os.getenv("REKASSA_API_KEY")
REKASSA_URL = os.getenv("REKASSA_URL")

REKASSA_TIMEZONE = "+05:00"
_SHIFT_LOCKS = {}
_SHIFT_LOCKS_GUARD = threading.Lock()


def _response_json(response):
    try:
        return response.json()
    except ValueError:
        return {"message": response.text or "Пустой ответ reKassa"}


def _api_error_message(payload, fallback="Ошибка reKassa"):
    if isinstance(payload, dict):
        return (
            payload.get("message")
            or payload.get("error")
            or payload.get("code")
            or fallback
        )
    return fallback


def _is_api_error(payload):
    return (
        isinstance(payload, dict)
        and payload.get("code")
        and payload.get("status") != "OK"
    )


def _shift_lock(company_id):
    with _SHIFT_LOCKS_GUARD:
        return _SHIFT_LOCKS.setdefault(company_id, threading.Lock())


def _load_company_rekassa():
    """Load credentials server-side and issue a fresh partner token."""
    from models import get_db, pool

    company_id = session.get("company_id")
    if not session.get("user_id"):
        return None, (jsonify({
            "success": False,
            "error": "Требуется войти в систему"
        }), 401)
    if not company_id:
        return None, (jsonify({
            "success": False,
            "error": "Активная организация не выбрана"
        }), 403)

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT *
            FROM integrations
            WHERE company_id = %s
            LIMIT 1
        """, (company_id,))
        row = cur.fetchone()
        integration = dict(row) if row else None
    finally:
        pool.putconn(conn)

    if (
        not integration
        or not integration.get("rekassa_enabled")
        or not integration.get("rekassa_number")
        or not integration.get("rekassa_password")
    ):
        return None, (jsonify({
            "success": False,
            "error": "reKassa не настроена для этой организации"
        }), 400)

    try:
        auth = requests.post(
            f"{REKASSA_URL}/api/auth/login",
            params={"apiKey": REKASSA_API_KEY, "format": "json"},
            json={
                "number": integration["rekassa_number"],
                "password": integration["rekassa_password"]
            },
            timeout=30
        )
    except requests.RequestException:
        return None, (jsonify({
            "success": False,
            "error": "Не удалось подключиться к reKassa"
        }), 502)

    auth_data = _response_json(auth)
    token = auth_data.get("token") if isinstance(auth_data, dict) else None
    crs_id = integration.get("rekassa_crs_id") or (
        auth_data.get("id") if isinstance(auth_data, dict) else None
    )

    if auth.status_code >= 400 or not token or not crs_id:
        return None, (jsonify({
            "success": False,
            "error": _api_error_message(auth_data, "Не удалось войти в reKassa")
        }), 502)

    return {
        "company_id": company_id,
        "integration": integration,
        "auth": auth_data,
        "token": token,
        "crs_id": crs_id
    }, None


def _rekassa_api(context, method, path, *, json_body=None, params=None,
                  password=False, request_id=False):
    headers = {
        "Authorization": f"Bearer {context['token']}",
        "Content-Type": "application/json",
        "timezone": REKASSA_TIMEZONE
    }
    if password:
        # True is retained for configuration calls made with the integration
        # password. A string is the one-time cash-register PIN entered by the
        # cashier and must never be persisted.
        headers["cash-register-password"] = (
            context["integration"]["rekassa_password"]
            if password is True
            else str(password)
        )
    if request_id:
        headers["X-Request-ID"] = str(uuid.uuid4())

    response = requests.request(
        method,
        f"{REKASSA_URL}{path}",
        headers=headers,
        params=params,
        json=json_body,
        timeout=30
    )
    return response, _response_json(response)


def _cash_register_from(payload):
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    candidates = (
        payload.get("cashRegister"),
        data.get("cashRegister"),
        payload
    )
    for candidate in candidates:
        if isinstance(candidate, dict) and any(
            key in candidate
            for key in ("shiftOpen", "shiftNumber", "configuration", "data")
        ):
            return candidate
    return {}


def _configuration_from(register, payload=None):
    register_data = (
        register.get("data")
        if isinstance(register.get("data"), dict)
        else {}
    )
    configuration = register_data.get("configuration")
    if not isinstance(configuration, dict):
        configuration = register.get("configuration")
    if not isinstance(configuration, dict) and isinstance(payload, dict):
        configuration = payload.get("configuration")
    return dict(configuration) if isinstance(configuration, dict) else {}


def _register_state(context):
    """Read current shift/configuration, with partner API fallbacks."""
    attempts = [
        f"/api/crs/{context['crs_id']}/with-roles",
        f"/api/crs/{context['crs_id']}"
    ]
    last_response = None
    last_payload = None

    for path in attempts:
        response, payload = _rekassa_api(context, "GET", path)
        last_response, last_payload = response, payload
        if response.status_code < 400 and not _is_api_error(payload):
            register = _cash_register_from(payload)
            if register:
                return {
                    "register": register,
                    "configuration": _configuration_from(register, payload),
                    "payload": payload
                }, None

    register = _cash_register_from(context.get("auth") or {})
    if register:
        return {
            "register": register,
            "configuration": _configuration_from(register, context.get("auth")),
            "payload": context.get("auth")
        }, None

    status = last_response.status_code if last_response is not None else 502
    return None, (jsonify({
        "success": False,
        "error": _api_error_message(
            last_payload,
            "Не удалось получить состояние смены reKassa"
        )
    }), status if 400 <= status < 600 else 502)


def _safe_shift_state(state, context):
    register = state["register"]
    configuration = state["configuration"]
    shift = register.get("shift") if isinstance(register.get("shift"), dict) else {}
    schedule = configuration.get("closeShiftSchedule")
    return {
        "connected": True,
        "crs_id": context["crs_id"],
        "serial_number": context["integration"].get("rekassa_serial_number"),
        "name": configuration.get("name") or register.get("name") or "reKassa",
        "shift_open": bool(register.get("shiftOpen")),
        "shift_number": register.get("shiftNumber") or shift.get("shiftNumber"),
        "shift": {
            "open_time": shift.get("openTime"),
            "close_time": shift.get("closeTime"),
            "ticket_count": shift.get("ticketCount"),
            "status": shift.get("status")
        },
        "auto_close": {
            "enabled": bool(schedule),
            "time": schedule,
            "email": configuration.get("closeShiftEmail"),
            "locale": configuration.get("closeShiftLocale") or "ru",
            "withdraw_money": bool(configuration.get("withdrawMoney"))
        },
        "timezone": "Asia/Almaty"
    }


def _cash_register_meta(state, context):
    """Return only printable public requisites; never expose credentials."""
    register = state.get("register") or {}
    register_data = (
        register.get("data")
        if isinstance(register.get("data"), dict)
        else {}
    )
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    payload_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    organization = register.get("organization")
    if not isinstance(organization, dict):
        organization = payload.get("organization")
    if not isinstance(organization, dict):
        organization = payload_data.get("organization")
    if not isinstance(organization, dict):
        organization = {}

    pos = register.get("pos")
    if not isinstance(pos, dict):
        pos = register_data.get("pos")
    if not isinstance(pos, dict):
        pos = {}

    serial_number = (
        register.get("serialNumber")
        or register_data.get("serialNumber")
        or context["integration"].get("rekassa_serial_number")
    )
    is_test = "test" in (REKASSA_URL or "").lower()
    fdo = register.get("fdo") or register_data.get("fdo") or "REK"

    return {
        "business_name": (
            organization.get("businessName")
            or organization.get("title")
            or organization.get("name")
        ),
        "business_id": (
            organization.get("businessId")
            or organization.get("inn")
            or organization.get("bin")
        ),
        "address": (
            pos.get("address")
            or organization.get("address")
        ),
        "registration_number": (
            register.get("registrationNumber")
            or register_data.get("registrationNumber")
            or register.get("fnsKkmId")
            or register_data.get("fnsKkmId")
        ),
        "serial_number": serial_number,
        "model": register.get("model") or register_data.get("model") or "reKassa 3.0",
        "fdo_code": fdo,
        "fdo_title": "ОФД ТОО «COMRUN»",
        "fdo_url": "https://ofd-test.rekassa.kz" if is_test else "https://ofd.rekassa.kz"
    }


def _report_core(payload):
    if not isinstance(payload, dict):
        return {}
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def _closed_shift_report(payload, shift_number):
    core = _report_core(payload)
    payload_number = payload.get("shiftNumber") if isinstance(payload, dict) else None
    report_number = payload_number or core.get("shiftNumber")
    close_time = (
        (payload.get("closeTime") if isinstance(payload, dict) else None)
        or core.get("closeShiftTime")
        or core.get("closeTime")
    )
    return bool(close_time and str(report_number or shift_number) == str(shift_number))


def _rekassa_print_url(crs_id, ticket_id):
    """Return the human-readable fiscal ticket URL for test or production."""
    parsed = urlsplit(REKASSA_URL or "")
    if not parsed.scheme or not parsed.netloc or not crs_id or not ticket_id:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/print/{crs_id}/{ticket_id}"

@rekassa_bp.route("/api/rekassa/login", methods=["POST"])
def rekassa_login():

    data = request.json

    response = requests.post(
        f"{REKASSA_URL}/api/auth/login",
        params={
            "apiKey": REKASSA_API_KEY,
            "format": "json"
        },
        json={
            "number": data["number"],
            "password": data["password"]
        },
        timeout=30
    )

    return jsonify(response.json()), response.status_code
    
@rekassa_bp.route("/api/rekassa/test", methods=["GET"])
def rekassa_test():
    return jsonify({
        "status": "ok",
        "api_key": bool(REKASSA_API_KEY),
        "url": REKASSA_URL
    })
    
@rekassa_bp.route("/api/rekassa/test-login")
def test_login():

    PASSWORD = os.getenv("REKASSA_PASSWORD")
    NUMBER = os.getenv("REKASSA_NUMBER")

    response = requests.post(
        f"{REKASSA_URL}/api/auth/login",
        params={
            "apiKey": REKASSA_API_KEY,
            "format": "json"
        },
        json={
            "number": NUMBER,
            "password": PASSWORD
        },
        timeout=30
    )

    return jsonify({
        "status": response.status_code,
        "response": response.json()
    })
    
@rekassa_bp.route("/api/rekassa/test-ticket")
def rekassa_test_ticket():

    # Логинимся
    auth = requests.post(
        f"{REKASSA_URL}/api/auth/login",
        params={
            "apiKey": REKASSA_API_KEY,
            "format": "json"
        },
        json={
            "number": os.getenv("REKASSA_NUMBER"),
            "password": os.getenv("REKASSA_PASSWORD")
        },
        timeout=30
    )

    auth_data = auth.json()

    token = auth_data["token"]
    crs_id = auth_data["id"]
    
    now = datetime.now()

    ticket = {
        "operation": "OPERATION_SELL",

        "dateTime": {
            "date": {
                "year": now.year,
                "month": now.month,
                "day": now.day
            },
            "time": {
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second
            }
        },

        "domain": {
            "type": "DOMAIN_SERVICES"
        },

        "items": [
            {
                "type": "ITEM_TYPE_COMMODITY",
                "commodity": {
                    "name": "Тестовый товар",
                    "sectionCode": "1",
                    "quantity": 1000,
                    "price": {
                        "bills": "100",
                        "coins": 0
                    },
                    "sum": {
                        "bills": "100",
                        "coins": 0
                    },
                    "auxiliary": [
                        {
                            "key": "UNIT_TYPE",
                            "value": "PIECE"
                        }
                    ]
                }
            }
        ],

        "payments": [
            {
                "type": "PAYMENT_CASH",
                "sum": {
                    "bills": "100",
                    "coins": 0
                }
            }
        ],

        "amounts": {
            "total": {
                "bills": "100",
                "coins": 0
            },
            "taken": {
                "bills": "100",
                "coins": 0
            },
            "change": {
                "bills": "0",
                "coins": 0
            }
        },

        "operator": {
            "code": 0
        }
    }

    response = requests.post(
        f"{REKASSA_URL}/api/crs/{crs_id}/tickets",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-ID": str(uuid.uuid4())
        },
        json=ticket,
        timeout=30
    )

    return jsonify({
        "status": response.status_code,
        "response": response.json()
    })
    
@rekassa_bp.route("/api/rekassa/save", methods=["POST"])
def save_rekassa():

    from models import get_db

    data = request.get_json(silent=True) or {}
    company_id = session.get("company_id")

    if not company_id:
        return jsonify({
            "success": False,
            "error": "Активная организация не выбрана"
        }), 403

    number = data.get("number")
    password = data.get("password")
    crs_id = data.get("id")
    serial_number = data.get("serialNumber")

    if not number or not password or not crs_id:
        return jsonify({
            "success": False,
            "error": "ReKassa вернула неполные данные кассы"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        # У старых организаций строка integrations обычно уже существует.
        # Для новой организации её может ещё не быть, поэтому одного UPDATE
        # недостаточно: он молча обновляет 0 строк.
        cur.execute("""
            UPDATE integrations
            SET
                rekassa_enabled = TRUE,
                rekassa_number = %s,
                rekassa_password = %s,
                rekassa_crs_id = %s,
                rekassa_serial_number = %s
            WHERE company_id = %s
        """, (
            number,
            password,
            crs_id,
            serial_number,
            company_id
        ))

        created = cur.rowcount == 0

        if created:
            cur.execute("""
                INSERT INTO integrations (
                    company_id,
                    rekassa_enabled,
                    rekassa_number,
                    rekassa_password,
                    rekassa_crs_id,
                    rekassa_serial_number,
                    created_at
                )
                VALUES (%s, TRUE, %s, %s, %s, %s, NOW())
            """, (
                company_id,
                number,
                password,
                crs_id,
                serial_number
            ))

        conn.commit()
    except Exception:
        conn.rollback()
        return jsonify({
            "success": False,
            "error": "Не удалось сохранить настройки ReKassa для организации"
        }), 500

    return jsonify({
        "success": True,
        "company_id": company_id,
        "created": created
    })
    
def rekassa_sell(conn, sale_id):

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM sales
        WHERE id = %s
    """, (
        sale_id,
    ))

    sale = cur.fetchone()
    
    cur.execute("""
        SELECT *
        FROM integrations
        WHERE company_id = %s
    """, (
        sale["company_id"],
    ))

    integration = cur.fetchone()

    if (
        not integration
        or not integration["rekassa_enabled"]
        or not integration["rekassa_number"]
        or not integration["rekassa_password"]
    ):
        return {
            "status": "ERROR",
            "message": "ReKassa не настроена для этой компании"
        }

    cur.execute("""
        SELECT *
        FROM sale_items
        WHERE sale_id = %s
    """, (
        sale_id,
    ))

    items = cur.fetchall()

    auth = requests.post(
        f"{REKASSA_URL}/api/auth/login",
        params={
            "apiKey": REKASSA_API_KEY,
            "format": "json"
        },
        json={
            "number": integration["rekassa_number"],
            "password": integration["rekassa_password"]
        },
        timeout=30
    )
    
    print("AUTH STATUS =", auth.status_code)
    print("AUTH TEXT =", auth.text)

    auth_data = auth.json()

    token = auth_data["token"]

    crs_id = integration["rekassa_crs_id"]

    now = datetime.now()

    ticket_items = []

    total = 0

    for item in items:

        amount = int(item["total"])

        total += amount
        
        commodity = {
            "name": item["name"],
            "sectionCode": "1",
            "quantity": int(item["quantity"] * 1000),

            "price": {
                "bills": str(int(item["price"])),
                "coins": 0
            },

            "sum": {
                "bills": str(amount),
                "coins": 0
            },

            "measureUnitCode": "796",

            "auxiliary": [
                {
                    "key": "UNIT_TYPE",
                    "value": "PIECE"
                }
            ]
        }

        if item.get("gtin"):
            commodity["barcode"] = str(item.get("gtin"))

        if item.get("ntin"):
            commodity["ntin"] = str(item.get("ntin"))

        if item.get("excise_stamp"):
            commodity["excise_stamp"] = item.get("excise_stamp")

        ticket_items.append({
            "type": "ITEM_TYPE_COMMODITY",
            "commodity": commodity
        })
        
    payment_type = "PAYMENT_CASH"

    if sale["sale_type"] == "card":
        payment_type = "PAYMENT_CARD"

    elif sale["sale_type"] == "kaspi":
        payment_type = "PAYMENT_CARD"
        
    amounts = {
        "total": {
            "bills": str(total),
            "coins": 0
        }
    }
    
    if payment_type == "PAYMENT_CASH":

        amounts["taken"] = {
            "bills": str(total),
            "coins": 0
        }

        amounts["change"] = {
            "bills": "0",
            "coins": 0
        }
    
    ticket = {

        "operation": "OPERATION_SELL",

        "dateTime": {
            "date": {
                "year": now.year,
                "month": now.month,
                "day": now.day
            },
            "time": {
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second
            }
        },

        "domain": {
            "type": "DOMAIN_SERVICES"
        },

        "items": ticket_items,

        "payments": [
            {
                "type": payment_type,
                "sum": {
                    "bills": str(total),
                    "coins": 0
                }
            }
        ],

        "amounts": amounts,

        "operator": {
            "code": 0
        }
    }

    response = requests.post(
        f"{REKASSA_URL}/api/crs/{crs_id}/tickets",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-ID": str(uuid.uuid4())
        },
        json=ticket,
        timeout=30
    )
    
    print("TICKET STATUS =", response.status_code)
    print("TICKET TEXT =", response.text)
    
    result = response.json()

    if result.get("status") == "OK":

        cur.execute("""
            UPDATE sales
            SET
                rekassa_ticket_id = %s,
                rekassa_ticket_number = %s,
                rekassa_qr = %s,
                rekassa_shift_number = %s,
                rekassa_status = %s
            WHERE id = %s
        """, (
            result.get("id"),
            result.get("ticketNumber"),
            result.get("qrCode"),
            result.get("shiftNumber"),
            result.get("status"),
            sale_id
        ))

        conn.commit()

    return result

    return response.json()
    
def rekassa_refund(conn, sale_id):

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM sales
        WHERE id = %s
    """, (sale_id,))

    sale = cur.fetchone()
    
    print("TICKET ID =", sale.get("rekassa_ticket_id"))
    print("TICKET NUMBER =", sale.get("rekassa_ticket_number"))
    print("DOCUMENT NUMBER =", sale.get("rekassa_document_number"))
    print("RNM =", sale.get("rekassa_rnm"))
    print("ZNM =", sale.get("rekassa_znm"))

    cur.execute("""
        SELECT *
        FROM integrations
        WHERE company_id = %s
    """, (sale["company_id"],))

    integration = cur.fetchone()

    if (
        not integration
        or not integration["rekassa_enabled"]
        or not integration["rekassa_number"]
        or not integration["rekassa_password"]
    ):
        return {
            "status": "ERROR",
            "message": "ReKassa не настроена"
        }

    cur.execute("""
        SELECT *
        FROM sale_items
        WHERE sale_id = %s
    """, (sale_id,))

    items = cur.fetchall()

    auth = requests.post(
        f"{REKASSA_URL}/api/auth/login",
        params={
            "apiKey": REKASSA_API_KEY,
            "format": "json"
        },
        json={
            "number": integration["rekassa_number"],
            "password": integration["rekassa_password"]
        },
        timeout=30
    )

    auth_data = auth.json()

    token = auth_data["token"]
    crs_id = integration["rekassa_crs_id"]

    # A fiscal return must reference the original fiscal ticket.  The sales
    # table keeps its id, but not the exact fiscal date/time, total and offline
    # flag, so obtain the complete original ticket from reKassa first.
    original_response = requests.get(
        f"{REKASSA_URL}/api/crs/{crs_id}/tickets/{sale['rekassa_ticket_id']}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        timeout=30
    )

    try:
        original_result = original_response.json()
    except ValueError:
        original_result = {}

    if original_response.status_code >= 400 or original_result.get("status") != "OK":
        return {
            "status": "ERROR",
            "message": "Не удалось получить исходный фискальный чек reKassa",
            "details": original_result or original_response.text
        }

    original_ticket = (
        (original_result.get("data") or {}).get("ticket") or {}
    )
    original_kkm = (
        (((original_result.get("data") or {}).get("service") or {})
         .get("regInfo") or {}).get("kkm") or {}
    )

    parent_ticket_number = (
        original_result.get("ticketNumber")
        or sale.get("rekassa_ticket_number")
    )
    parent_ticket_datetime = original_ticket.get("dateTime")
    parent_kgd_kkm_id = (
        original_kkm.get("fnsKkmId")
        or sale.get("rekassa_rnm")
    )
    parent_ticket_total = (
        (original_ticket.get("amounts") or {}).get("total")
    )

    if not all((
        parent_ticket_number,
        parent_ticket_datetime,
        parent_kgd_kkm_id,
        parent_ticket_total
    )):
        return {
            "status": "ERROR",
            "message": "В исходном чеке reKassa не хватает реквизитов для возврата"
        }

    parent_ticket = {
        "parentTicketNumber": str(parent_ticket_number),
        "parentTicketDataTime": parent_ticket_datetime,
        "kgdKkmId": str(parent_kgd_kkm_id),
        "parentTicketTotal": parent_ticket_total,
        "parentTicketIsOffline": bool(original_result.get("offline", False))
    }

    now = datetime.now()

    ticket_items = []
    total = 0

    for item in items:
        amount = int(item["total"])
        total += amount

        commodity = {
            "name": item["name"],
            "sectionCode": "1",
            "quantity": int(item["quantity"] * 1000),
            "price": {
                "bills": str(int(item["price"])),
                "coins": 0
            },
            "sum": {
                "bills": str(amount),
                "coins": 0
            },
            "measureUnitCode": "796",
            "auxiliary": [
                {
                    "key": "UNIT_TYPE",
                    "value": "PIECE"
                }
            ]
        }

        if item.get("gtin"):
            commodity["barcode"] = str(item.get("gtin"))

        if item.get("ntin"):
            commodity["ntin"] = str(item.get("ntin"))

        ticket_items.append({
            "type": "ITEM_TYPE_COMMODITY",
            "commodity": commodity
        })

    payment_type = "PAYMENT_CASH"

    if sale["sale_type"] in ["card", "kaspi", "invoice"]:
        payment_type = "PAYMENT_CARD"

    amounts = {
        "total": {
            "bills": str(total),
            "coins": 0
        }
    }

    # Для наличного возврата поле taken обязательно, но должно быть равно нулю:
    # деньги выдаются покупателю, а не принимаются от него. Возвращаемая сумма
    # уже указана в payments[].sum.
    if payment_type == "PAYMENT_CASH":
        amounts["taken"] = {
            "bills": "0",
            "coins": 0
        }
        amounts["change"] = {
            "bills": "0",
            "coins": 0
        }

    ticket = {
        "operation": "OPERATION_SELL_RETURN",

        "dateTime": {
            "date": {
                "year": now.year,
                "month": now.month,
                "day": now.day
            },
            "time": {
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second
            }
        },

        "domain": {
            "type": "DOMAIN_SERVICES"
        },

        "items": ticket_items,

        "payments": [
            {
                "type": payment_type,
                "sum": {
                    "bills": str(total),
                    "coins": 0
                }
            }
        ],

        "amounts": amounts,

        "parentTicket": parent_ticket,

        "operator": {
            "code": 0
        }
    }
    
    print("=" * 50)
    print("REKASSA REFUND REQUEST")
    print(
        json.dumps(
            ticket,
            indent=2,
            ensure_ascii=False
        )
    )
    print("=" * 50)

    response = requests.post(
        f"{REKASSA_URL}/api/crs/{crs_id}/tickets",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-ID": str(uuid.uuid4())
        },
        json=ticket,
        timeout=30
    )
    
    print("=" * 50)
    print("REKASSA REFUND RESPONSE")
    print(
        json.dumps(
            response.json(),
            indent=2,
            ensure_ascii=False
        )
    )
    print("=" * 50)

    result = response.json()

    # Keep local metadata next to the immutable fiscal response.  sales.py
    # stores this JSON so the completed refund can always be opened again from
    # history without confusing the original sale ticket with the return one.
    if result.get("status") == "OK":
        result["_nika"] = {
            "crs_id": crs_id,
            "source_ticket_id": sale.get("rekassa_ticket_id"),
            "print_url": _rekassa_print_url(crs_id, result.get("id"))
        }

    return result


@rekassa_bp.route("/api/rekassa/shift/status", methods=["GET"])
def rekassa_shift_status():
    context, error = _load_company_rekassa()
    if error:
        return error
    try:
        state, error = _register_state(context)
    except requests.RequestException:
        return jsonify({
            "success": False,
            "error": "Не удалось получить состояние смены reKassa"
        }), 502
    if error:
        return error
    return jsonify({
        "success": True,
        **_safe_shift_state(state, context),
        "cash_register": _cash_register_meta(state, context)
    })


@rekassa_bp.route("/api/rekassa/reports/x", methods=["POST"])
def rekassa_x_report():
    context, error = _load_company_rekassa()
    if error:
        return error
    try:
        state, error = _register_state(context)
        if error:
            return error
        register = state["register"]
        shift_number = register.get("shiftNumber") or (
            (register.get("shift") or {}).get("shiftNumber")
            if isinstance(register.get("shift"), dict)
            else None
        )
        if not register.get("shiftOpen") or not shift_number:
            return jsonify({
                "success": False,
                "error": "Смена закрыта. X-отчёт доступен только для открытой смены"
            }), 409

        response, payload = _rekassa_api(
            context,
            "GET",
            f"/api/crs/{context['crs_id']}/shifts/{shift_number}/reports/x"
        )
    except requests.RequestException:
        return jsonify({
            "success": False,
            "error": "reKassa не ответила при формировании X-отчёта"
        }), 502

    if response.status_code >= 400 or _is_api_error(payload):
        return jsonify({
            "success": False,
            "error": _api_error_message(payload, "Не удалось сформировать X-отчёт")
        }), response.status_code if response.status_code >= 400 else 400

    return jsonify({
        "success": True,
        "report_type": "X",
        "shift_number": shift_number,
        "report": payload,
        "cash_register": _cash_register_meta(state, context)
    })


@rekassa_bp.route("/api/rekassa/shifts/close", methods=["POST"])
def rekassa_close_shift():
    context, error = _load_company_rekassa()
    if error:
        return error

    with _shift_lock(context["company_id"]):
        try:
            state, error = _register_state(context)
            if error:
                return error
            register = state["register"]
            shift = register.get("shift") if isinstance(register.get("shift"), dict) else {}
            shift_number = register.get("shiftNumber") or shift.get("shiftNumber")

            if not register.get("shiftOpen") or not shift_number:
                return jsonify({
                    "success": False,
                    "error": "Смена уже закрыта"
                }), 409

            data = request.get_json(silent=True) or {}
            cash_register_pin = str(data.get("pin") or "").strip()
            register_status = str(
                register.get("status")
                or (state.get("payload") or {}).get("status")
                or ""
            ).upper()

            if register_status and register_status != "TRIAL" and not cash_register_pin:
                return jsonify({
                    "success": False,
                    "error": "Введите PIN ККМ для закрытия смены"
                }), 400
            if len(cash_register_pin) > 64:
                return jsonify({
                    "success": False,
                    "error": "Некорректный PIN ККМ"
                }), 400

            withdraw_money = data.get("withdraw_money")
            if withdraw_money is None:
                withdraw_money = bool(
                    state["configuration"].get("withdrawMoney")
                )

            params = {"withdrawMoney": "true"} if withdraw_money else None
            response, payload = _rekassa_api(
                context,
                "POST",
                f"/api/crs/{context['crs_id']}/shifts/{shift_number}/close",
                json_body={},
                params=params,
                password=cash_register_pin or False,
                request_id=True
            )
        except requests.RequestException:
            return jsonify({
                "success": False,
                "error": "reKassa не ответила при закрытии смены"
            }), 502

        if response.status_code >= 400 or _is_api_error(payload):
            return jsonify({
                "success": False,
                "error": _api_error_message(payload, "Не удалось закрыть смену")
            }), response.status_code if response.status_code >= 400 else 400

        # A 2xx response alone is not enough: verify that reKassa returned a
        # closed Z-report. If the close command is processed just after the
        # response, briefly re-read the immutable closed shift.
        closed_report = payload if _closed_shift_report(payload, shift_number) else None
        if closed_report is None:
            for attempt in range(3):
                if attempt:
                    time.sleep(0.35)
                try:
                    check_response, check_payload = _rekassa_api(
                        context,
                        "GET",
                        f"/api/crs/{context['crs_id']}/shifts/{shift_number}"
                    )
                except requests.RequestException:
                    continue
                if (
                    check_response.status_code < 400
                    and not _is_api_error(check_payload)
                    and _closed_shift_report(check_payload, shift_number)
                ):
                    closed_report = check_payload
                    break

        if closed_report is None:
            return jsonify({
                "success": False,
                "error": (
                    "reKassa приняла запрос, но смена осталась открытой. "
                    "Проверьте PIN ККМ и повторите закрытие"
                )
            }), 409

        return jsonify({
            "success": True,
            "message": f"Смена №{shift_number} закрыта",
            "report_type": "Z",
            "shift_number": shift_number,
            "report": closed_report,
            "cash_register": _cash_register_meta(state, context)
        })


@rekassa_bp.route("/api/rekassa/shifts", methods=["GET"])
def rekassa_shift_history():
    context, error = _load_company_rekassa()
    if error:
        return error

    try:
        page = max(int(request.args.get("page", 0)), 0)
        size = min(max(int(request.args.get("size", 20)), 1), 100)
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "Некорректные параметры страницы"
        }), 400

    try:
        response, payload = _rekassa_api(
            context,
            "GET",
            f"/api/crs/{context['crs_id']}/shifts",
            params={"includeOpen": "false", "page": page, "size": size}
        )
    except requests.RequestException:
        return jsonify({
            "success": False,
            "error": "Не удалось загрузить историю смен reKassa"
        }), 502

    if response.status_code >= 400 or _is_api_error(payload):
        return jsonify({
            "success": False,
            "error": _api_error_message(payload, "Не удалось загрузить историю смен")
        }), response.status_code if response.status_code >= 400 else 400

    return jsonify({"success": True, "history": payload})


@rekassa_bp.route(
    "/api/rekassa/shifts/<int:shift_number>/report",
    methods=["GET"]
)
def rekassa_z_report(shift_number):
    context, error = _load_company_rekassa()
    if error:
        return error
    try:
        response, payload = _rekassa_api(
            context,
            "GET",
            f"/api/crs/{context['crs_id']}/shifts/{shift_number}"
        )
    except requests.RequestException:
        return jsonify({
            "success": False,
            "error": "Не удалось загрузить Z-отчёт reKassa"
        }), 502

    if response.status_code >= 400 or _is_api_error(payload):
        return jsonify({
            "success": False,
            "error": _api_error_message(payload, "Z-отчёт не найден")
        }), response.status_code if response.status_code >= 400 else 404

    return jsonify({
        "success": True,
        "report_type": "Z",
        "shift_number": shift_number,
        "report": payload
    })


@rekassa_bp.route("/api/rekassa/auto-close", methods=["PUT"])
def rekassa_save_auto_close():
    context, error = _load_company_rekassa()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled"))
    schedule = (data.get("time") or "").strip() if enabled else None

    if enabled and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule):
        return jsonify({
            "success": False,
            "error": "Укажите время в формате ЧЧ:ММ"
        }), 400

    try:
        state, error = _register_state(context)
        if error:
            return error
        if state["register"].get("shiftOpen"):
            return jsonify({
                "success": False,
                "error": (
                    "reKassa разрешает менять автозакрытие только при закрытой смене. "
                    "Сначала сформируйте Z-отчёт"
                )
            }), 409

        configuration = dict(state["configuration"])
        if not configuration:
            return jsonify({
                "success": False,
                "error": "reKassa не вернула текущую конфигурацию кассы"
            }), 502

        configuration["closeShiftSchedule"] = schedule
        configuration["closeShiftScheduleWithdrawMoney"] = bool(
            configuration.get("withdrawMoney")
        )

        if "email" in data:
            email = (data.get("email") or "").strip() or None
            configuration["closeShiftEmail"] = email
            configuration["closeShiftLocale"] = "ru" if email else None

        response, payload = _rekassa_api(
            context,
            "PUT",
            f"/api/crs/{context['crs_id']}/configuration",
            json_body=configuration,
            password=True,
            request_id=True
        )
    except requests.RequestException:
        return jsonify({
            "success": False,
            "error": "reKassa не ответила при сохранении автозакрытия"
        }), 502

    if response.status_code >= 400 or _is_api_error(payload):
        return jsonify({
            "success": False,
            "error": _api_error_message(
                payload,
                "Не удалось сохранить настройку автозакрытия"
            )
        }), response.status_code if response.status_code >= 400 else 400

    return jsonify({
        "success": True,
        "message": (
            f"Автозакрытие установлено на {schedule}"
            if enabled
            else "Автозакрытие отключено"
        ),
        "auto_close": {
            "enabled": enabled,
            "time": schedule,
            "email": configuration.get("closeShiftEmail"),
            "timezone": "Asia/Almaty"
        }
    })
    

    
