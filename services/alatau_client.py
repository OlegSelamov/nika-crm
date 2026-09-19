import os
import re

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
            os.getenv("NIKA_INTEGRATION_ENCRYPTION_KEY")
            or os.getenv("ALATAU_TOKEN_ENCRYPTION_KEY")
            or os.getenv("BCC_TOKEN_ENCRYPTION_KEY")
            or ""
        ).strip()
        if not key:
            raise AlatauConfigurationError(
                "На сервере не задан NIKA_INTEGRATION_ENCRYPTION_KEY"
            )
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise AlatauConfigurationError(
                "NIKA_INTEGRATION_ENCRYPTION_KEY имеет неверный формат"
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

    def __init__(self):
        self.base_url = (
            os.getenv("ALATAU_BUSINESS_API_BASE_URL")
            or "https://business.alataucitybank.kz/jbapi"
        ).rstrip("/")
        self.timeout = int(os.getenv("ALATAU_HTTP_TIMEOUT", "30"))
        self.user_agent = (
            os.getenv("ALATAU_USER_AGENT")
            or "NikaBusiness/1.0 (+https://nikabusiness.com)"
        ).strip()

    @staticmethod
    def configuration_status():
        encryption_key = (
            os.getenv("NIKA_INTEGRATION_ENCRYPTION_KEY")
            or os.getenv("ALATAU_TOKEN_ENCRYPTION_KEY")
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

    @staticmethod
    def _content_type(response):
        return (response.headers.get("Content-Type") or "").lower()

    @staticmethod
    def _incident_id(response):
        text = response.text or ""
        match = re.search(r"incident\s+id\s+is\s*:\s*([^<\r\n]+)", text, re.I)
        if match:
            return match.group(1).strip().rstrip(".")[:120]
        return None

    @classmethod
    def _error_message(cls, response, fallback):
        payload = cls._json(response)
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, str) and error:
                description = payload.get("error_description") or payload.get("description")
                message = f"{error}: {description}" if description else error
                return f"HTTP {response.status_code}. {message}"[:500]
            if isinstance(error, dict):
                description = error.get("description") or error.get("message")
                code = error.get("code")
                details = error.get("details")
                first_detail = None
                if isinstance(details, list) and details:
                    first = details[0]
                    if isinstance(first, dict):
                        detail_message = first.get("message") or first.get("description")
                        detail_code = first.get("code")
                        if detail_message:
                            first_detail = (
                                f"{detail_code}: {detail_message}"
                                if detail_code else str(detail_message)
                            )
                if description:
                    prefix = f"{code}: " if code else ""
                    suffix = f" · {first_detail}" if first_detail else ""
                    return (
                        f"HTTP {response.status_code}. {prefix}{description}{suffix}"
                    )[:500]
                if first_detail:
                    return f"HTTP {response.status_code}. {first_detail}"[:500]
            message = (
                payload.get("message")
                or payload.get("description")
                or payload.get("error_description")
            )
            if message:
                return f"HTTP {response.status_code}. {message}"[:500]

        content_type = cls._content_type(response)
        body = (response.text or "").lower()
        if "text/html" in content_type or "<html" in body:
            incident_id = cls._incident_id(response)
            suffix = f" Incident ID: {incident_id}." if incident_id else ""
            return (
                f"Firewall Alatau City Bank отклонил запрос (HTTP {response.status_code})."
                f"{suffix} Передайте этот статус/Incident ID поддержке Business API."
            )[:500]

        return f"HTTP {response.status_code}. {fallback}"[:500]

    def _headers(self, *, with_json=False, access_token=None):
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "Connection": "close",
        }
        if with_json:
            headers["Content-Type"] = "application/json"
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def authenticate(self, client_id, client_secret):
        if not client_id or not client_secret:
            raise AlatauError("Укажите Client ID и Client Secret", status_code=400)

        url = f"{self.base_url}/v1/oauth/token"
        try:
            response = requests.post(
                url,
                json={"clientId": client_id, "clientSecret": client_secret},
                headers=self._headers(with_json=True),
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise AlatauError(
                "Не удалось соединиться с Alatau City Bank. Проверьте доступ VPS к business.alataucitybank.kz"
            ) from exc

        if 300 <= response.status_code < 400:
            location = response.headers.get("Location") or "не указан"
            raise AlatauError(
                f"Alatau API неожиданно перенаправил запрос (HTTP {response.status_code}, Location: {location})",
                status_code=502,
            )

        payload = self._json(response)
        access_token = payload.get("accessToken") if isinstance(payload, dict) else None
        company_id = payload.get("companyId") if isinstance(payload, dict) else None
        if response.status_code >= 400 or not access_token or not company_id:
            status_code = (
                response.status_code
                if response.status_code in (400, 401, 403, 404, 412, 424, 429)
                else 502
            )
            raise AlatauError(
                self._error_message(
                    response,
                    "Банк не выдал accessToken/companyId для переданных Client ID / Client Secret",
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
                headers=self._headers(
                    with_json=json is not None,
                    access_token=access_token,
                ),
                params=params,
                json=json,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise AlatauError(
                f"Alatau City Bank не ответил за {self.timeout} сек. Повторите запрос; если ошибка повторяется, проверьте доступ VPS к business.alataucitybank.kz",
                status_code=504,
            ) from exc
        except requests.ConnectionError as exc:
            raise AlatauError(
                "VPS не смог установить соединение с Alatau City Bank. Это сетевая ошибка между сервером Nika и API банка.",
                status_code=502,
            ) from exc
        except requests.RequestException as exc:
            raise AlatauError(
                f"Ошибка соединения с Alatau City Bank: {exc.__class__.__name__}",
                status_code=502,
            ) from exc

        if 300 <= response.status_code < 400:
            location = response.headers.get("Location") or "не указан"
            raise AlatauError(
                f"Alatau API перенаправил запрос (HTTP {response.status_code}, Location: {location})",
                status_code=502,
            )

        payload = self._json(response)
        if response.status_code >= 400:
            status_code = (
                response.status_code
                if response.status_code in (400, 401, 403, 404, 412, 424, 429)
                else 502
            )
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

    def get_accounts_cards(self, access_token, company_id):
        return self.request(
            "GET",
            f"/v3/companies/{company_id}/accounts/cards",
            access_token,
        )

    def get_dictionary(self, access_token, code):
        return self.request(
            "GET",
            "/v1/dictionaries",
            access_token,
            params={"code": code},
        )

    def get_banks(self, access_token):
        return self.request(
            "GET",
            "/v1/dictionaries/banks",
            access_token,
        )

    def create_contractor_draft(self, access_token, company_id, payload):
        return self.request(
            "POST",
            f"/v2/companies/{company_id}/payments",
            access_token,
            json=payload,
        )

    def send_signed_payment(self, access_token, company_id, content):
        return self.request(
            "POST",
            f"/v2/companies/{company_id}/signed-payments",
            access_token,
            json={"content": content},
        )

    def get_payment_status(self, access_token, company_id, operation_id):
        return self.request(
            "GET",
            f"/v1/companies/{company_id}/payments/{operation_id}/status",
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
