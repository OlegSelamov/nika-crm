import os
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
from cryptography.fernet import Fernet, InvalidToken


class BCCError(Exception):
    """Безопасная для интерфейса ошибка интеграции BCC."""

    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class BCCConfigurationError(BCCError):
    def __init__(self, message):
        super().__init__(message, status_code=503)


class BCCTokenCipher:
    """Шифрует клиентские access/refresh-токены перед записью в PostgreSQL."""

    def __init__(self):
        key = (os.getenv("BCC_TOKEN_ENCRYPTION_KEY") or "").strip()
        if not key:
            raise BCCConfigurationError(
                "На сервере не задан BCC_TOKEN_ENCRYPTION_KEY"
            )
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise BCCConfigurationError(
                "BCC_TOKEN_ENCRYPTION_KEY имеет неверный формат"
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
            raise BCCConfigurationError(
                "Не удалось расшифровать токен BCC. Проверьте ключ шифрования"
            ) from exc


class BCCClient:
    APP_SCOPE_DEFAULT = "bcc.application.business.account.management"
    CLIENT_SCOPE_DEFAULT = "oapi.business.account.api"
    PRODUCT_CODE = "BusinessApi"

    _app_token = None
    _app_token_expires_at = 0
    _app_token_lock = threading.Lock()

    def __init__(self):
        environment = (os.getenv("BCC_ENVIRONMENT") or "sandbox").strip().lower()
        hosts = {
            "sandbox": "https://api-sandbox.bcc.kz",
            "test": "https://api-test.bcc.kz",
            "production": "https://api.bcc.kz",
        }
        if environment not in hosts:
            raise BCCConfigurationError(
                "BCC_ENVIRONMENT должен быть sandbox, test или production"
            )

        host = hosts[environment]
        self.environment = environment
        self.client_id = (os.getenv("BCC_CLIENT_ID") or "").strip()
        self.client_secret = (os.getenv("BCC_CLIENT_SECRET") or "").strip()
        self.callback_url = (
            os.getenv("BCC_CALLBACK_URL")
            or "https://nikabusiness.com/api/integrations/bcc/callback"
        ).strip()
        self.app_scope = (
            os.getenv("BCC_APP_SCOPE") or self.APP_SCOPE_DEFAULT
        ).strip()
        self.client_scope = (
            os.getenv("BCC_CLIENT_SCOPE") or self.CLIENT_SCOPE_DEFAULT
        ).strip()
        self.oauth_token_url = (
            os.getenv("BCC_OAUTH_TOKEN_URL")
            or f"{host}/bcc/production/v2/oauth/token"
        ).rstrip("/")
        self.auth_base_url = (
            os.getenv("BCC_AUTH_BASE_URL")
            or f"{host}/bcc/production/v1/auth-client"
        ).rstrip("/")
        self.accounts_base_url = (
            os.getenv("BCC_ACCOUNTS_BASE_URL")
            or f"{host}/bcc/production/v2/business-account-management"
        ).rstrip("/")
        self.timeout = int(os.getenv("BCC_HTTP_TIMEOUT", "30"))

        missing = []
        if not self.client_id:
            missing.append("BCC_CLIENT_ID")
        if not self.client_secret:
            missing.append("BCC_CLIENT_SECRET")
        if missing:
            raise BCCConfigurationError(
                "На сервере не заданы: " + ", ".join(missing)
            )

    @staticmethod
    def configuration_status():
        required = (
            "BCC_CLIENT_ID",
            "BCC_CLIENT_SECRET",
            "BCC_TOKEN_ENCRYPTION_KEY",
        )
        missing = [name for name in required if not os.getenv(name)]
        return {
            "configured": not missing,
            "missing": missing,
            "environment": (os.getenv("BCC_ENVIRONMENT") or "sandbox").lower(),
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
            message = (
                payload.get("error_description")
                or payload.get("message")
                or payload.get("error")
            )
            if message:
                return str(message)[:500]
        return fallback

    def get_app_token(self, force=False):
        now = time.time()
        if (
            not force
            and self.__class__._app_token
            and self.__class__._app_token_expires_at > now + 30
        ):
            return self.__class__._app_token

        with self.__class__._app_token_lock:
            now = time.time()
            if (
                not force
                and self.__class__._app_token
                and self.__class__._app_token_expires_at > now + 30
            ):
                return self.__class__._app_token

            data = {
                "grant_type": "client_credentials",
                "scope": self.app_scope,
            }
            try:
                response = requests.post(
                    self.oauth_token_url,
                    data=data,
                    auth=(self.client_id, self.client_secret),
                    headers={"Accept": "application/json"},
                    timeout=self.timeout,
                )

                # Некоторые конфигурации IBM API Connect принимают учётные
                # данные приложения только как поля формы.
                first_payload = self._json(response)
                if (
                    response.status_code in (400, 401)
                    and not (
                        isinstance(first_payload, dict)
                        and first_payload.get("access_token")
                    )
                ):
                    response = requests.post(
                        self.oauth_token_url,
                        data={
                            **data,
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                        },
                        headers={"Accept": "application/json"},
                        timeout=self.timeout,
                    )
            except requests.RequestException as exc:
                raise BCCError("BCC сейчас недоступен. Повторите попытку позже") from exc

            payload = self._json(response)
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if response.status_code >= 400 or not token:
                raise BCCError(
                    self._error_message(
                        response,
                        "BCC не принял ключ API или пароль приложения",
                    ),
                    status_code=502,
                )

            try:
                expires_in = max(int(payload.get("expires_in", 300)), 60)
            except (TypeError, ValueError):
                expires_in = 300
            self.__class__._app_token = token
            self.__class__._app_token_expires_at = time.time() + expires_in
            return token

    def _app_headers(self):
        return {
            "Authorization": f"Bearer {self.get_app_token()}",
            "Accept": "application/json",
        }

    def generate_auth_url(self, client_idn, lang="ru"):
        try:
            response = requests.post(
                f"{self.auth_base_url}/generate-auth-url",
                data={
                    "redirect_uri": self.callback_url,
                    "client_idn": client_idn,
                    "lang": lang,
                    "scope": self.client_scope,
                },
                headers=self._app_headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise BCCError("Не удалось открыть авторизацию BCC") from exc

        payload = self._json(response)
        auth_url = payload.get("authUrl") if isinstance(payload, dict) else None
        if response.status_code >= 400 or not auth_url:
            raise BCCError(
                self._error_message(response, "BCC не сформировал ссылку авторизации")
            )
        return auth_url

    def exchange_authorization_code(self, code):
        return self._client_token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.callback_url,
                "client_secret": self.client_secret,
            }
        )

    def refresh_client_token(self, refresh_token):
        return self._client_token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_secret": self.client_secret,
            }
        )

    def _client_token_request(self, data):
        try:
            response = requests.post(
                f"{self.auth_base_url}/token",
                data=data,
                headers=self._app_headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise BCCError("Не удалось получить клиентский токен BCC") from exc

        payload = self._json(response)
        if (
            response.status_code >= 400
            or not isinstance(payload, dict)
            or not payload.get("access_token")
        ):
            raise BCCError(
                self._error_message(response, "BCC не выдал клиентский токен")
            )
        return payload

    def revoke_client_token(self, token):
        if not token:
            return
        try:
            response = requests.post(
                f"{self.auth_base_url}/revoke",
                data={"token": token},
                headers=self._app_headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise BCCError("Не удалось отозвать токен в BCC") from exc
        if response.status_code >= 400:
            raise BCCError(
                self._error_message(response, "BCC не подтвердил отзыв доступа")
            )

    def account_request(self, method, path, client_token, *, params=None):
        if not client_token:
            raise BCCError("Подключение BCC не завершено", status_code=409)
        headers = self._app_headers()
        headers.update(
            {
                "x-client-token": client_token,
                "productCode": self.PRODUCT_CODE,
            }
        )
        try:
            response = requests.request(
                method,
                f"{self.accounts_base_url}{path}",
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise BCCError("Не удалось получить данные из BCC") from exc

        payload = self._json(response)
        if response.status_code >= 400:
            status_code = 401 if response.status_code in (401, 403) else 502
            raise BCCError(
                self._error_message(response, "BCC вернул ошибку при получении данных"),
                status_code=status_code,
            )
        return payload

    def get_accounts(self, client_token):
        return self.account_request("GET", "/accounts", client_token)

    def get_statement(
        self,
        client_token,
        iban,
        date_from,
        date_to,
        currency,
        *,
        offset=0,
        limit=100,
    ):
        return self.account_request(
            "GET",
            f"/accounts/{quote(iban, safe='')}/statements/pages",
            client_token,
            params={
                "date_from": date_from,
                "date_to": date_to,
                "currency": currency,
                "convert_kaz": "false",
                "offset": offset,
                "limit": limit,
            },
        )


def token_expiry(payload):
    try:
        seconds = max(int(payload.get("expires_in", 300)), 60)
    except (TypeError, ValueError):
        seconds = 300
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
