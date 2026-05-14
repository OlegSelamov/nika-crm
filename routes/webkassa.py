import os
import requests
import urllib3

from flask import Blueprint

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

webkassa_bp = Blueprint(
    "webkassa",
    __name__
)

WEBKASSA_API_KEY = os.getenv(
    "WEBKASSA_API_KEY"
)

BASE_URL = "https://kkm.webkassa.kz/api"


@webkassa_bp.route("/test-webkassa")
def test_webkassa():

    headers = {
        "X-API-KEY": WEBKASSA_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "operation": "buy",

        "positions": [
            {
                "name": "Тестовый товар",
                "price": 1000,
                "quantity": 1,
                "sum": 1000
            }
        ],

        "payments": [
            {
                "type": "cash",
                "sum": 1000
            }
        ]
    }

    response = requests.post(
        f"{BASE_URL}/checks",
        json=data,
        headers=headers,
        verify=False
    )

    return response.text