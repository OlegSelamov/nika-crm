import os

import requests
from cryptography.fernet import Fernet, InvalidToken


class AlatauError(Exception):
    """Безопасная для интерфейса ошибка Alatau City Bank Business API."""

    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class AlatauConfigurationError(AlatauError):
    def __init__(self, message):
        super().__init__(message, status_code=503)


class AlatauSecretCipher:
    """Шифрует client_secret организации перед записью в PostgreSQL."""

    def __init__(self):
        key = (
            os.getenv("ALATAU_TOKEN_ENCRYPTION_KEY")
            or os.getenv("BCC_TOKEN_ENCRYPTION_KEY")
            or ""
        ).strip()
        if not key:
            raise AlatauConfigurationError(
                "На сервере не задан ALATAU_TOKEN_ENCRYPTION_KEY"
            )
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise AlatauConfigurationError(
                "ALATAU_TOKEN_ENCRYPTION_KEY имеет неверный формат"
            ) from exc

    def encrypt(self, value):
        if not value:
            return None
        return self._fernet.encrypt(str(value).encode("utf-8")).decode("utf-8")

    def decrypt(self, value):
        if not value:
            return None
        try:
            return self._fernet.decrypt(
                str(value).encode("utf-8")
            ).decode("utf-8")
        except InvalidToken as exc:
            raise AlatauConfigurationError(
                "Не удалось расшифровать Client Secret Alatau City Bank"
            ) from exc


class AlatauClient:
    """Минимальный клиент Business API Alatau City Bank."""

    SANDBOX_CLIENT_ID = "client_id_test"
    SANDBOX_CLIENT_SECRET = "client_secret_test"

    def __init__(self):
        self.base_url = (
            os.getenv("ALATAU_BUSINESS_API_BASE_URL")
            or "https://business.alataucitybank.kz/jbapi"
        ).rstrip("/")
        self.timeout = int(os.getenv("ALATAU_HTTP_TIMEOUT", "30"))

    @staticmethod
    def configuration_status():
        encryption_key = (
            os.getenv("ALATAU_TOKEN_ENCRYPTION_KEY")
            or os.getenv("BCC_TOKEN_ENCRYPTION_KEY")
            or ""
        ).strip()
        return {
            "base_url": (
                os.getenv("ALATAU_BUSINESS_API_BASE_URL")
                or "https://business.alataucitybank.kz/jbapi"
            ).rstrip("/"),
            "secret_storage_configured": bool(encryption_key),
        }

    @staticmethod
    def _json(response):
        try:
            return response.json()
        except ValueError:
            return {}

    @classmethod
    def _error_message(cls, response, fallback):
        payload = cls._json(response)
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                description = error.get("description") or error.get("message")
                if description:
                    return str(description)[:500]
                details = error.get("details")
                if isinstance(details, list) and details:
                    first = details[0]
                    if isinstance(first, dict) and first.get("message"):
                        return str(first["message"])[:500]
            message = payload.get("message") or payload.get("description")
            if message:
                return str(message)[:500]
        return fallback

    def authenticate(self, client_id, client_secret):
        if not client_id or not client_secret:
            raise AlatauError("Укажите Client ID и Client Secret", status_code=400)
        try:
            response = requests.post(
                f"{self.base_url}/v1/oauth/token",
                json={"clientId": client_id, "clientSecret": client_secret},
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AlatauError(
                "Alatau City Bank сейчас недоступен. Повторите попытку позже"
            ) from exc

        payload = self._json(response)
        access_token = payload.get("accessToken") if isinstance(payload, dict) else None
        company_id = payload.get("companyId") if isinstance(payload, dict) else None
        if response.status_code >= 400 or not access_token or not company_id:
            status_code = 401 if response.status_code in (401, 403) else 502
            raise AlatauError(
                self._error_message(
                    response,
                    "Банк не принял Client ID / Client Secret",
                ),
                status_code=status_code,
            )
        return payload

    def request(self, method, path, access_token, *, params=None, json=None):
        if not access_token:
            raise AlatauError("Нет авторизационного токена", status_code=401)
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                params=params,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AlatauError(
                "Не удалось получить данные из Alatau City Bank"
            ) from exc

        payload = self._json(response)
        if response.status_code >= 400:
            status_code = 401 if response.status_code in (401, 403) else 502
            raise AlatauError(
                self._error_message(
                    response,
                    "Alatau City Bank вернул ошибку при получении данных",
                ),
                status_code=status_code,
            )
        return payload

    def get_accounts(self, access_token, company_id):
        return self.request(
            "GET",
            f"/v1/companies/{company_id}/accounts",
            access_token,
        )

    def get_statement(
        self,
        access_token,
        company_id,
        iban,
        date_from,
        date_to,
        *,
        page=1,
        page_size=100,
    ):
        return self.request(
            "GET",
            f"/v3/companies/{company_id}/statements",
            access_token,
            params={
                "iban": iban,
                "dateFrom": date_from,
                "dateTo": date_to,
                "page": page,
                "pageSize": page_size,
            },
        )
