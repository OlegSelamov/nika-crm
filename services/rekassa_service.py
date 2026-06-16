# services/rekassa_service.py
import requests
import os

REKASSA_API_KEY = os.getenv("REKASSA_API_KEY")
REKASSA_URL = "https://app-test.rekassa.kz/partner"


def login(number, password):
    response = requests.post(
        f"{REKASSA_URL}/api/auth/login",
        params={
            "apiKey": REKASSA_API_KEY,
            "format": "json"
        },
        json={
            "number": number,
            "password": password
        },
        timeout=30
    )

    return response.json()