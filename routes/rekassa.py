from flask import Blueprint, request, jsonify, session
from datetime import datetime
import requests
import os
import uuid
import json
from urllib.parse import urlsplit

rekassa_bp = Blueprint("rekassa", __name__)

REKASSA_API_KEY = os.getenv("REKASSA_API_KEY")
REKASSA_URL = os.getenv("REKASSA_URL")


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
    

    
