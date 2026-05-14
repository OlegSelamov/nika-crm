import os
import ssl
import requests
import urllib3

from flask import Blueprint
from requests.adapters import HTTPAdapter
from urllib3 import poolmanager

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


class TLSAdapter(HTTPAdapter):

    def init_poolmanager(
        self,
        connections,
        maxsize,
        block=False,
        **pool_kwargs
    ):

        ctx = ssl.create_default_context()
        
        ctx.check_hostname = False

        # 🔥 старый TLS для WebKassa
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")

        # отключаем TLS 1.3
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2

        pool_kwargs["ssl_context"] = ctx

        self.poolmanager = poolmanager.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **pool_kwargs
        )


session = requests.Session()

session.mount(
    "https://",
    TLSAdapter()
)


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
                "name": "Тест",
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

    response = session.post(
        f"{BASE_URL}/checks",
        json=data,
        headers=headers,
        verify=False
    )

    return f"""
    STATUS: {response.status_code}

    HEADERS:
    {dict(response.headers)}

    BODY:
    {response.text}
    """