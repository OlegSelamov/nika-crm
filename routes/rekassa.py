from flask import Blueprint, request, jsonify, session
from datetime import datetime
import requests
import os
import uuid

rekassa_bp = Blueprint("rekassa", __name__)

REKASSA_API_KEY = os.getenv("REKASSA_API_KEY")
REKASSA_URL = os.getenv("REKASSA_URL")

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

    data = request.json

    conn = get_db()
    cur = conn.cursor()

    company_id = session.get("company_id")

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
        data["number"],
        data["password"],
        data["id"],
        data["serialNumber"],
        company_id
    ))

    conn.commit()

    return jsonify({
        "success": True
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

        "operator": {
            "code": 0
        }
    }
    
    print("=" * 50)
    print("REKASSA REFUND REQUEST")
    print(ticket)
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
    print(response.json())
    print("=" * 50)

    return response.json()
    

    
