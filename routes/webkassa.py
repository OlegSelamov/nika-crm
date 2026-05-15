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

        ctx.set_ciphers(
            "DEFAULT@SECLEVEL=0"
        )

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


API_KEY = os.getenv(
    "WEBKASSA_API_KEY"
)


@webkassa_bp.route("/test-webkassa")
def test_webkassa():

    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    response = session.post(

        "https://devkkm.webkassa.kz/api/v4/Authorize",

        headers=headers,

        json={

            "Login": "shelamov1997@gmail.com",

            "Password": "Kk12345#@",

            "GrantType": "0000"

        },

        verify=False
    )

    data = response.json()

    token = data["Data"]["Token"]

    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    check_data = {

        "Token": token,

        "CashboxUniqueNumber": "SWK00035407",

        "CheckData": {
            "TypeOperation": 1
        },

        "Positions": [
            {
                "Count": 1,
                "Price": 1000,
                "Tax": 0,
                "Text": "Тестовый товар"
            }
        ],

        "Payments": [
            {
                "Sum": 1000,
                "PaymentType": 0
            }
        ]
    }
    
    check_response = session.post(

        "https://devkkm.webkassa.kz/api/v4/Check",

        headers=headers,

        json=check_data,

        verify=False
    )

    return str(check_response.json())