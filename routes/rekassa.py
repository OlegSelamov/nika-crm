from flask import Blueprint, request, jsonify
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
    
