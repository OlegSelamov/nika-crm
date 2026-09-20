import base64
import hashlib
import json
import logging
import re
import secrets
import time
from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template, request, session, redirect
from models import get_db, pool
from services.alatau_client import AlatauClient, AlatauError, AlatauSecretCipher

# Imported for startup side effects: installs stock quantity sync, duplicate
# identifier protection and stock consistency diagnostic endpoints.
import routes.stock_consistency  # noqa: F401

settings_bp = Blueprint("settings", __name__)
logger = logging.getLogger(__name__)


def _alatau_current_company():
    if not session.get("user_id"):
        return None, (jsonify({"success": False, "error": "Требуется войти"}), 401)
    company_id = session.get("company_id")
    if not company_id:
        return None, (jsonify({"success": False, "error": "Организация не выбрана"}), 403)
    if not (
        session.get("is_super_admin")
        or session.get("role") in ("owner", "admin", "creator")
    ):
        return None, (jsonify({"success": False, "error": "Доступ разрешён владельцу"}), 403)
    return company_id, None


def _alatau_csrf_token():
    token = session.get("alatau_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["alatau_csrf_token"] = token
    return token


def _alatau_valid_csrf():
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("alatau_csrf_token")
    return bool(supplied and expected and secrets.compare_digest(supplied, expected))


def _ensure_alatau_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alatau_integrations (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            environment TEXT NOT NULL DEFAULT 'test',
            client_id TEXT,
            client_secret_encrypted TEXT,
            access_token_encrypted TEXT,
            token_expires_at TIMESTAMPTZ,
            bank_company_id TEXT,
            status TEXT NOT NULL DEFAULT 'disconnected',
            connected_at TIMESTAMPTZ,
            last_checked_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        ALTER TABLE alatau_integrations
        ADD COLUMN IF NOT EXISTS access_token_encrypted TEXT
    """)
    cur.execute("""
        ALTER TABLE alatau_integrations
        ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMPTZ
    """)
    cur.execute("""
        ALTER TABLE alatau_integrations
        DROP CONSTRAINT IF EXISTS alatau_integrations_company_id_key
    """)
    cur.execute("""
        UPDATE alatau_integrations
        SET environment = 'test'
        WHERE environment = 'sandbox'
          AND NOT EXISTS (
              SELECT 1
              FROM alatau_integrations x
              WHERE x.company_id = alatau_integrations.company_id
                AND x.environment = 'test'
          )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_alatau_integrations_company
        ON alatau_integrations(company_id)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_alatau_integrations_company_environment
        ON alatau_integrations(company_id, environment)
    """)


def _ensure_bank_payment_templates_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_payment_templates (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            iin_bin TEXT,
            iban TEXT,
            bic TEXT,
            kbe TEXT,
            knp TEXT,
            purpose TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bank_payment_templates_company
        ON bank_payment_templates(company_id, updated_at DESC)
    """)


def _ensure_alatau_payment_history_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alatau_payment_history (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            environment TEXT NOT NULL DEFAULT 'production',
            operation_id TEXT,
            payment_type TEXT,
            payer_iban TEXT,
            receiver_name TEXT,
            receiver_iin_bin TEXT,
            receiver_iban TEXT,
            receiver_bic TEXT,
            kbe TEXT,
            knp TEXT,
            kbk TEXT,
            period_start TEXT,
            period_end TEXT,
            amount NUMERIC(18,2),
            currency TEXT NOT NULL DEFAULT 'KZT',
            document_number TEXT,
            purpose TEXT,
            status_code TEXT NOT NULL DEFAULT 'CREATED',
            status_message TEXT,
            bank_status_timestamp TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE alatau_payment_history ADD COLUMN IF NOT EXISTS kbe TEXT")
    cur.execute("ALTER TABLE alatau_payment_history ADD COLUMN IF NOT EXISTS knp TEXT")
    cur.execute("ALTER TABLE alatau_payment_history ADD COLUMN IF NOT EXISTS kbk TEXT")
    cur.execute("ALTER TABLE alatau_payment_history ADD COLUMN IF NOT EXISTS period_start TEXT")
    cur.execute("ALTER TABLE alatau_payment_history ADD COLUMN IF NOT EXISTS period_end TEXT")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_alatau_payment_history_operation
        ON alatau_payment_history(company_id, environment, operation_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_alatau_payment_history_company_created
        ON alatau_payment_history(company_id, created_at DESC)
    """)


def _alatau_payment_result_fields(result):
    payload = result if isinstance(result, dict) else {}
    payment = payload.get("payment") if isinstance(payload.get("payment"), dict) else payload
    operation_id = (
        payment.get("operationId")
        or payment.get("operation_id")
        or payload.get("operationId")
        or payload.get("operation_id")
    )
    status = payment.get("status") or payload.get("status") or "CREATED"
    if isinstance(status, dict):
        status_code = str(status.get("code") or "CREATED")
        status_message = str(status.get("message") or "")
        status_timestamp = status.get("timestamp")
    else:
        status_code = str(status or "CREATED")
        status_message = ""
        status_timestamp = None
    return operation_id, status_code, status_message, status_timestamp


def _alatau_store_payment(company_id, environment, meta, result=None, *,
                          fallback_status="CREATED", fallback_message=""):
    meta = meta or {}
    operation_id, status_code, status_message, status_timestamp = (
        _alatau_payment_result_fields(result)
    )
    if not status_code or status_code == "CREATED":
        status_code = fallback_status
    if not status_message:
        status_message = fallback_message

    amount = meta.get("amount")
    try:
        amount = round(float(amount), 2) if amount not in (None, "") else None
    except (TypeError, ValueError):
        amount = None

    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_alatau_payment_history_table(cur)
        cur.execute("""
            INSERT INTO alatau_payment_history (
                company_id, environment, operation_id, payment_type,
                payer_iban, receiver_name, receiver_iin_bin,
                receiver_iban, receiver_bic, kbe, knp, kbk, period_start,
                period_end, amount, currency, document_number, purpose,
                status_code, status_message,
                bank_status_timestamp, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, 'KZT', %s, %s, %s, %s, %s, NOW(), NOW()
            )
            ON CONFLICT (company_id, environment, operation_id) DO UPDATE SET
                payment_type = COALESCE(EXCLUDED.payment_type, alatau_payment_history.payment_type),
                payer_iban = COALESCE(EXCLUDED.payer_iban, alatau_payment_history.payer_iban),
                receiver_name = COALESCE(EXCLUDED.receiver_name, alatau_payment_history.receiver_name),
                receiver_iin_bin = COALESCE(EXCLUDED.receiver_iin_bin, alatau_payment_history.receiver_iin_bin),
                receiver_iban = COALESCE(EXCLUDED.receiver_iban, alatau_payment_history.receiver_iban),
                receiver_bic = COALESCE(EXCLUDED.receiver_bic, alatau_payment_history.receiver_bic),
                kbe = COALESCE(EXCLUDED.kbe, alatau_payment_history.kbe),
                knp = COALESCE(EXCLUDED.knp, alatau_payment_history.knp),
                kbk = COALESCE(EXCLUDED.kbk, alatau_payment_history.kbk),
                period_start = COALESCE(EXCLUDED.period_start, alatau_payment_history.period_start),
                period_end = COALESCE(EXCLUDED.period_end, alatau_payment_history.period_end),
                amount = COALESCE(EXCLUDED.amount, alatau_payment_history.amount),
                document_number = COALESCE(EXCLUDED.document_number, alatau_payment_history.document_number),
                purpose = COALESCE(EXCLUDED.purpose, alatau_payment_history.purpose),
                status_code = EXCLUDED.status_code,
                status_message = EXCLUDED.status_message,
                bank_status_timestamp = COALESCE(EXCLUDED.bank_status_timestamp, alatau_payment_history.bank_status_timestamp),
                updated_at = NOW()
            RETURNING id
        """, (
            company_id,
            environment,
            operation_id,
            meta.get("paymentType"),
            meta.get("accountIban"),
            meta.get("receiverName"),
            meta.get("receiverIinBin"),
            meta.get("receiverIban"),
            meta.get("receiverBic"),
            meta.get("kbe"),
            meta.get("knp"),
            meta.get("kbk"),
            meta.get("periodStart"),
            meta.get("periodEnd"),
            amount,
            meta.get("documentNumber"),
            meta.get("purpose"),
            status_code[:120],
            (status_message or "")[:500] or None,
            status_timestamp or None,
        ))
        row = cur.fetchone()
        conn.commit()
        return row.get("id") if isinstance(row, dict) else (row[0] if row else None)
    except Exception:
        conn.rollback()
        return None
    finally:
        pool.putconn(conn)


def _alatau_row(company_id, environment):
    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_alatau_table(cur)
        conn.commit()
        cur.execute(
            """
            SELECT *
            FROM alatau_integrations
            WHERE company_id = %s AND environment = %s
            LIMIT 1
            """,
            (company_id, environment),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        pool.putconn(conn)


def _safe_alatau_row(row):
    if not row:
        return None
    return {
        "environment": row.get("environment"),
        "client_id": row.get("client_id"),
        "bank_company_id": row.get("bank_company_id"),
        "status": row.get("status"),
        "connected_at": row.get("connected_at"),
        "last_checked_at": row.get("last_checked_at"),
        "last_error": row.get("last_error"),
        "has_secret": bool(row.get("client_secret_encrypted")),
        "has_token": bool(row.get("access_token_encrypted")),
        "token_expires_at": row.get("token_expires_at"),
    }


@settings_bp.route("/settings")
def settings():

    if not session.get("user_id"):
        return redirect("/login")

    return render_template("settings.html")
    
@settings_bp.route("/settings/integrations")
def integrations():
    return render_template("settings/integrations.html")


@settings_bp.route("/banks")
def my_banks():
    company_id, error = _alatau_current_company()
    if error:
        if error[1] == 401:
            return redirect("/login")
        return redirect("/settings")

    integrations = {
        "test": _safe_alatau_row(_alatau_row(company_id, "test")),
        "production": _safe_alatau_row(_alatau_row(company_id, "production")),
    }

    # Юридические реквизиты берём из карточки организации Nika.
    # Банковские реквизиты (банк/БИК/IBAN) приходят отдельно из Alatau API.
    company_requisites = {}
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT name, address, bin, kbe
            FROM companies
            WHERE id = %s
            LIMIT 1
        """, (company_id,))
        row = cur.fetchone()
        company_requisites = dict(row) if row else {}
    finally:
        pool.putconn(conn)

    return render_template(
        "settings/alatau.html",
        alatau_integrations=integrations,
        alatau_config=AlatauClient.configuration_status(),
        csrf_token=_alatau_csrf_token(),
        bank_workspace=True,
        company_requisites=company_requisites,
    )


@settings_bp.route("/settings/integrations/alatau")
def alatau_settings():
    company_id, error = _alatau_current_company()
    if error:
        if error[1] == 401:
            return redirect("/login")
        return redirect("/settings/integrations")

    integrations = {
        "test": _safe_alatau_row(_alatau_row(company_id, "test")),
        "production": _safe_alatau_row(_alatau_row(company_id, "production")),
    }

    return render_template(
        "settings/alatau.html",
        alatau_integrations=integrations,
        alatau_config=AlatauClient.configuration_status(),
        csrf_token=_alatau_csrf_token(),
    )


@settings_bp.route("/api/integrations/alatau/test", methods=["POST"])
def alatau_test_connection():
    company_id, error = _alatau_current_company()
    if error:
        return error
    if not _alatau_valid_csrf():
        return jsonify({"success": False, "error": "Страница устарела. Обновите её"}), 403

    environment = (request.form.get("environment") or "test").strip().lower()
    if environment not in ("test", "production"):
        return jsonify({"success": False, "error": "Неверный режим подключения"}), 400

    existing = _alatau_row(company_id, environment) or {}
    client = AlatauClient()

    if environment == "test":
        client_id = "client_id_test"
        client_secret = "client_secret_test"
    else:
        client_id = (request.form.get("client_id") or existing.get("client_id") or "").strip()
        client_secret = (request.form.get("client_secret") or "").strip()
        if not client_secret and existing.get("client_secret_encrypted"):
            try:
                client_secret = AlatauSecretCipher().decrypt(
                    existing.get("client_secret_encrypted")
                )
            except AlatauError as exc:
                return jsonify({"success": False, "error": str(exc)}), exc.status_code
        if not client_id or not client_secret:
            return jsonify({"success": False, "error": "Укажите Client ID и Client Secret"}), 400

    try:
        auth = client.authenticate(client_id, client_secret)
        bank_company_id = auth.get("companyId")
        access_token = auth.get("accessToken")
        accounts = client.get_accounts(access_token, bank_company_id)

        cipher = AlatauSecretCipher()
        encrypted_secret = cipher.encrypt(client_secret)
        encrypted_token = cipher.encrypt(access_token)
        expires_in = auth.get("expiresIn") or auth.get("expires_in") or 3600
        try:
            expires_in = max(int(expires_in), 60)
        except (TypeError, ValueError):
            expires_in = 3600

        conn = get_db()
        try:
            cur = conn.cursor()
            _ensure_alatau_table(cur)
            cur.execute("""
                INSERT INTO alatau_integrations (
                    company_id, environment, client_id, client_secret_encrypted,
                    access_token_encrypted, token_expires_at,
                    bank_company_id, status, connected_at, last_checked_at,
                    last_error, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, NOW() + (%s || ' seconds')::interval,
                    %s, 'connected', NOW(), NOW(), NULL, NOW()
                )
                ON CONFLICT (company_id, environment) DO UPDATE SET
                    environment = EXCLUDED.environment,
                    client_id = EXCLUDED.client_id,
                    client_secret_encrypted = COALESCE(
                        EXCLUDED.client_secret_encrypted,
                        alatau_integrations.client_secret_encrypted
                    ),
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    token_expires_at = EXCLUDED.token_expires_at,
                    bank_company_id = EXCLUDED.bank_company_id,
                    status = 'connected',
                    connected_at = COALESCE(alatau_integrations.connected_at, NOW()),
                    last_checked_at = NOW(),
                    last_error = NULL,
                    updated_at = NOW()
            """, (
                company_id,
                environment,
                client_id,
                encrypted_secret,
                encrypted_token,
                str(expires_in),
                bank_company_id,
            ))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)

        if isinstance(accounts, list):
            account_count = len(accounts)
        elif isinstance(accounts, dict):
            account_count = len(accounts.get("accounts") or accounts.get("data") or [])
        else:
            account_count = 0

        return jsonify({
            "success": True,
            "environment": environment,
            "company_id": bank_company_id,
            "accounts": account_count,
            "message": "Соединение с Alatau City Bank успешно",
        })
    except AlatauError as exc:
        error_message = str(exc)
        if environment == "test" and exc.status_code == 401:
            error_message = (
                "Песочница Alatau City Bank отклонила официальные TEST-реквизиты "
                "client_id_test / client_secret_test (HTTP 401). "
                "Запрос Nika соответствует опубликованной спецификации банка. "
                "Повторите проверку позже или используйте Production с ключами вашего приложения."
            )

        conn = get_db()
        try:
            cur = conn.cursor()
            _ensure_alatau_table(cur)
            cur.execute("""
                INSERT INTO alatau_integrations (
                    company_id, environment, client_id, status,
                    last_checked_at, last_error, updated_at
                ) VALUES (%s, %s, %s, 'error', NOW(), %s, NOW())
                ON CONFLICT (company_id, environment) DO UPDATE SET
                    environment = EXCLUDED.environment,
                    client_id = COALESCE(EXCLUDED.client_id, alatau_integrations.client_id),
                    status = 'error',
                    last_checked_at = NOW(),
                    last_error = EXCLUDED.last_error,
                    updated_at = NOW()
            """, (
                company_id,
                environment,
                client_id or None,
                error_message[:500],
            ))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            pool.putconn(conn)
        return jsonify({"success": False, "error": error_message}), exc.status_code



def _alatau_touch(company_id, environment, *, bank_company_id=None, error=None):
    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_alatau_table(cur)
        cur.execute("""
            UPDATE alatau_integrations
            SET bank_company_id = COALESCE(%s, bank_company_id),
                last_checked_at = NOW(),
                last_error = %s,
                updated_at = NOW()
            WHERE company_id = %s AND environment = %s
        """, (bank_company_id, error, company_id, environment))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        pool.putconn(conn)


def _alatau_live_session(company_id, environment):
    environment = (environment or "test").strip().lower()
    if environment not in ("test", "production"):
        raise AlatauError("Неверный режим подключения", status_code=400)

    integration = _alatau_row(company_id, environment)
    if not integration or integration.get("status") != "connected":
        label = "TEST" if environment == "test" else "Production"
        raise AlatauError(
            f"Сначала подключите Alatau City Bank для среды {label}",
            status_code=409,
        )

    cipher = AlatauSecretCipher()
    client = AlatauClient()
    bank_company_id = integration.get("bank_company_id")

    access_token = None
    token_expires_at = integration.get("token_expires_at")
    if integration.get("access_token_encrypted") and token_expires_at:
        try:
            from datetime import datetime, timezone
            expiry = token_expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry > datetime.now(timezone.utc) + timedelta(seconds=30):
                access_token = cipher.decrypt(integration.get("access_token_encrypted"))
        except Exception:
            access_token = None

    if not access_token:
        client_id = (integration.get("client_id") or "").strip()
        encrypted_secret = integration.get("client_secret_encrypted")

        if environment == "test" and (not client_id or not encrypted_secret):
            client_id = "client_id_test"
            client_secret = "client_secret_test"
        else:
            if not client_id or not encrypted_secret:
                raise AlatauError(
                    "У подключения отсутствуют Client ID или Client Secret. Подключите банк повторно",
                    status_code=409,
                )
            client_secret = cipher.decrypt(encrypted_secret)

        auth = client.authenticate(client_id, client_secret)
        access_token = auth.get("accessToken")
        bank_company_id = auth.get("companyId")
        if not access_token or not bank_company_id:
            raise AlatauError(
                "Alatau City Bank не вернул accessToken/companyId",
                status_code=502,
            )

        expires_in = auth.get("expiresIn") or auth.get("expires_in") or 3600
        try:
            expires_in = max(int(expires_in), 60)
        except (TypeError, ValueError):
            expires_in = 3600

        conn = get_db()
        try:
            cur = conn.cursor()
            _ensure_alatau_table(cur)
            cur.execute("""
                UPDATE alatau_integrations
                SET access_token_encrypted = %s,
                    token_expires_at = NOW() + (%s || ' seconds')::interval,
                    bank_company_id = %s,
                    last_checked_at = NOW(),
                    last_error = NULL,
                    updated_at = NOW()
                WHERE company_id = %s AND environment = %s
            """, (
                cipher.encrypt(access_token),
                str(expires_in),
                bank_company_id,
                company_id,
                environment,
            ))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)

    _alatau_touch(
        company_id,
        environment,
        bank_company_id=bank_company_id,
        error=None,
    )
    return client, access_token, bank_company_id, environment


@settings_bp.route("/api/integrations/alatau/accounts")
def alatau_accounts():
    company_id, error = _alatau_current_company()
    if error:
        return error

    environment = (request.args.get("environment") or "test").strip().lower()
    try:
        client, access_token, bank_company_id, environment = _alatau_live_session(
            company_id, environment
        )
        try:
            payload = client.get_accounts(access_token, bank_company_id)
            endpoint = "v1"
        except AlatauError as first_exc:
            if first_exc.status_code not in (400, 404):
                raise
            payload = client.get_accounts_cards(access_token, bank_company_id)
            endpoint = "v3"

        if isinstance(payload, list):
            accounts = payload
        elif isinstance(payload, dict):
            accounts = payload.get("accounts") or payload.get("data") or payload.get("items")
            if accounts is None and payload.get("iban"):
                accounts = [payload]
            accounts = accounts or []
        else:
            accounts = []

        # Банк и БИК берём из справочника самого Alatau. Если справочник
        # временно недоступен, оставляем безопасный fallback для текущей интеграции.
        bank_info = {
            "name": "Alatau City Bank",
            "bic": "TSESKZKA",
        }
        try:
            bank_rows = client.get_banks(access_token)
            if isinstance(bank_rows, dict):
                bank_rows = (
                    bank_rows.get("content")
                    or bank_rows.get("items")
                    or bank_rows.get("data")
                    or bank_rows.get("banks")
                    or []
                )
            if isinstance(bank_rows, list):
                preferred = None
                for bank in bank_rows:
                    if not isinstance(bank, dict):
                        continue
                    bic = str(
                        bank.get("bic")
                        or bank.get("bankBic")
                        or bank.get("code")
                        or ""
                    ).replace(" ", "").upper()
                    name = str(
                        bank.get("name")
                        or bank.get("bankName")
                        or bank.get("fullName")
                        or ""
                    ).strip()
                    if bic == "TSESKZKA":
                        preferred = {"name": name or "Alatau City Bank", "bic": bic}
                        break
                    if not preferred and "ALATAU" in name.upper():
                        preferred = {"name": name, "bic": bic or "TSESKZKA"}
                if preferred:
                    bank_info = preferred
        except AlatauError:
            pass

        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        company_requisites = {}
        req_conn = get_db()
        try:
            req_cur = req_conn.cursor()
            req_cur.execute("""
                SELECT name, address, bin, kbe
                FROM companies
                WHERE id = %s
                LIMIT 1
            """, (company_id,))
            req_row = req_cur.fetchone()
            company_requisites = dict(req_row) if req_row else {}
        finally:
            pool.putconn(req_conn)

        return jsonify({
            "success": True,
            "environment": environment,
            "company_id": bank_company_id,
            "endpoint": endpoint,
            "accounts": accounts,
            "bank": bank_info,
            "company": company_requisites,
        })
    except AlatauError as exc:
        _alatau_touch(company_id, environment, error=str(exc)[:500])
        return jsonify({"success": False, "error": str(exc)}), exc.status_code



@settings_bp.route("/api/integrations/alatau/cards")
def alatau_cards():
    company_id, error = _alatau_current_company()
    if error:
        return error

    environment = (request.args.get("environment") or "production").strip().lower()
    try:
        client, access_token, bank_company_id, environment = _alatau_live_session(
            company_id, environment
        )
        payload = client.get_accounts_cards(access_token, bank_company_id)
        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        return jsonify({
            "success": True,
            "environment": environment,
            "company_id": bank_company_id,
            "data": payload,
        })
    except AlatauError as exc:
        _alatau_touch(company_id, environment, error=str(exc)[:500])
        return jsonify({"success": False, "error": str(exc)}), exc.status_code



@settings_bp.route("/api/integrations/alatau/dictionaries")
def alatau_dictionaries():
    company_id, error = _alatau_current_company()
    if error:
        return error

    environment = (request.args.get("environment") or "production").strip().lower()
    code = (request.args.get("code") or "KBE").strip().upper()
    if code not in ("KBE", "KNP", "KBK"):
        return jsonify({"success": False, "error": "Неверный код справочника"}), 400

    try:
        client, access_token, bank_company_id, environment = _alatau_live_session(
            company_id, environment
        )
        values = client.get_dictionary(access_token, code)
        banks = client.get_banks(access_token)
        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        return jsonify({
            "success": True,
            "environment": environment,
            "code": code,
            "values": values,
            "banks": banks,
        })
    except AlatauError as exc:
        _alatau_touch(company_id, environment, error=str(exc)[:500])
        return jsonify({"success": False, "error": str(exc)}), exc.status_code



@settings_bp.route("/api/integrations/alatau/payment-templates")
def alatau_payment_templates():
    company_id, error = _alatau_current_company()
    if error:
        return error

    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_bank_payment_templates_table(cur)
        conn.commit()
        cur.execute("""
            SELECT id, name, iin_bin, iban, bic, kbe, knp, purpose,
                   created_at, updated_at
            FROM bank_payment_templates
            WHERE company_id = %s
            ORDER BY updated_at DESC, id DESC
            LIMIT 200
        """, (company_id,))
        rows = cur.fetchall() or []

        templates = []
        for item in rows:
            row = dict(item) if not isinstance(item, dict) else item
            templates.append({
                "id": row.get("id"),
                "name": row.get("name") or "",
                "iinBin": row.get("iin_bin") or "",
                "iban": row.get("iban") or "",
                "bic": row.get("bic") or "",
                "kbe": row.get("kbe") or "",
                "knp": row.get("knp") or "",
                "purpose": row.get("purpose") or "",
                "createdAt": row.get("created_at").isoformat()
                    if row.get("created_at") else None,
                "updatedAt": row.get("updated_at").isoformat()
                    if row.get("updated_at") else None,
            })

        return jsonify({"success": True, "templates": templates})
    finally:
        pool.putconn(conn)


@settings_bp.route("/api/integrations/alatau/payment-templates", methods=["POST"])
def alatau_save_payment_template():
    company_id, error = _alatau_current_company()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    template_id = data.get("id")
    name = (data.get("name") or "").strip()
    iin_bin = (data.get("iinBin") or "").strip()
    iban = (data.get("iban") or "").replace(" ", "").upper()
    bic = (data.get("bic") or "").replace(" ", "").upper()
    kbe = (data.get("kbe") or "").strip()
    knp = (data.get("knp") or "").strip()
    purpose = (data.get("purpose") or "").strip()

    if not name:
        return jsonify({"success": False, "error": "Укажите название контрагента"}), 400
    if iin_bin and (len(iin_bin) != 12 or not iin_bin.isdigit()):
        return jsonify({"success": False, "error": "БИН/ИИН должен содержать 12 цифр"}), 400
    if iban and not re.fullmatch(r"KZ[A-Z0-9]{18}", iban):
        return jsonify({"success": False, "error": "Неверный IBAN контрагента"}), 400
    if bic and not re.fullmatch(r"[A-Z0-9]{8,11}", bic):
        return jsonify({"success": False, "error": "Неверный БИК"}), 400
    if kbe and (len(kbe) != 2 or not kbe.isdigit()):
        return jsonify({"success": False, "error": "КБЕ должен состоять из 2 цифр"}), 400
    if knp and (len(knp) != 3 or not knp.isdigit()):
        return jsonify({"success": False, "error": "КНП должен состоять из 3 цифр"}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_bank_payment_templates_table(cur)

        if template_id:
            cur.execute("""
                UPDATE bank_payment_templates
                SET name = %s,
                    iin_bin = %s,
                    iban = %s,
                    bic = %s,
                    kbe = %s,
                    knp = %s,
                    purpose = %s,
                    updated_at = NOW()
                WHERE id = %s AND company_id = %s
                RETURNING id
            """, (
                name, iin_bin or None, iban or None, bic or None,
                kbe or None, knp or None, purpose or None,
                template_id, company_id,
            ))
        else:
            cur.execute("""
                INSERT INTO bank_payment_templates (
                    company_id, name, iin_bin, iban, bic, kbe, knp, purpose,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (
                company_id, name, iin_bin or None, iban or None,
                bic or None, kbe or None, knp or None, purpose or None,
            ))

        row = cur.fetchone()
        if not row:
            conn.rollback()
            return jsonify({"success": False, "error": "Шаблон не найден"}), 404
        saved_id = row.get("id") if isinstance(row, dict) else row[0]
        conn.commit()
        return jsonify({
            "success": True,
            "id": saved_id,
            "message": "Шаблон платежа сохранён",
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@settings_bp.route("/api/integrations/alatau/payment-templates/<int:template_id>", methods=["DELETE"])
def alatau_delete_payment_template(template_id):
    company_id, error = _alatau_current_company()
    if error:
        return error

    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_bank_payment_templates_table(cur)
        cur.execute("""
            DELETE FROM bank_payment_templates
            WHERE id = %s AND company_id = %s
            RETURNING id
        """, (template_id, company_id))
        row = cur.fetchone()
        conn.commit()
        if not row:
            return jsonify({"success": False, "error": "Шаблон не найден"}), 404
        return jsonify({"success": True})
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)



def _alatau_dictionary_rows(payload):
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "items", "data", "values", "results"):
        nested = payload.get(key)
        if isinstance(nested, list):
            return [row for row in nested if isinstance(row, dict)]
        if isinstance(nested, dict):
            rows = _alatau_dictionary_rows(nested)
            if rows:
                return rows
    return []


def _alatau_dictionary_name(client, access_token, dictionary_code, value):
    rows = _alatau_dictionary_rows(
        client.get_dictionary(access_token, dictionary_code)
    )
    value = str(value or "").strip()
    for row in rows:
        row_code = str(
            row.get("code")
            or row.get("value")
            or row.get("id")
            or ""
        ).strip()
        if row_code != value:
            continue
        return str(
            row.get("name")
            or row.get("title")
            or row.get("description")
            or ""
        ).strip()
    return ""


def _alatau_valid_tax_period(value):
    value = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if not match:
        return False
    month = int(match.group(2))
    return 1 <= month <= 12


@settings_bp.route("/api/integrations/alatau/payments/tax/draft", methods=["POST"])
def alatau_tax_payment_draft():
    company_id, error = _alatau_current_company()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    environment = (data.get("environment") or "production").strip().lower()
    account_iban = (data.get("accountIban") or "").replace(" ", "").upper()
    knp = re.sub(r"\D", "", str(data.get("knp") or ""))[:3]
    kbk = re.sub(r"\D", "", str(data.get("kbk") or ""))[:6]
    period_start = str(data.get("periodStart") or "").strip()
    period_end = str(data.get("periodEnd") or "").strip()
    document_number = str(data.get("documentNumber") or "").strip()
    purpose = str(data.get("purpose") or "").strip()
    vin = re.sub(r"[^A-Za-z0-9]", "", str(data.get("vin") or "")).upper()[:17]
    protocol_number = str(data.get("protocolNumber") or "").strip()[:80]

    try:
        amount = round(float(data.get("amount")), 2)
    except (TypeError, ValueError):
        amount = 0

    if not re.fullmatch(r"KZ[A-Z0-9]{18}", account_iban):
        return jsonify({"success": False, "error": "Неверный счёт списания"}), 400
    if len(knp) != 3:
        return jsonify({"success": False, "error": "КНП должен содержать 3 цифры"}), 400
    if len(kbk) != 6:
        return jsonify({"success": False, "error": "КБК должен содержать 6 цифр"}), 400
    if not _alatau_valid_tax_period(period_start) or not _alatau_valid_tax_period(period_end):
        return jsonify({
            "success": False,
            "error": "Налоговый период укажите в формате ГГГГ-ММ",
        }), 400
    if period_start > period_end:
        return jsonify({
            "success": False,
            "error": "Начало налогового периода не может быть позже окончания",
        }), 400
    if amount <= 0:
        return jsonify({"success": False, "error": "Сумма должна быть больше 0"}), 400
    if not document_number:
        return jsonify({"success": False, "error": "Укажите номер документа"}), 400
    if kbk in ("104401", "104402") and not vin:
        return jsonify({
            "success": False,
            "error": "Для КБК 104401/104402 необходимо указать VIN",
        }), 400
    if kbk.startswith("204") and not protocol_number:
        return jsonify({
            "success": False,
            "error": "Для КБК 204*** необходимо указать номер протокола",
        }), 400

    try:
        client, access_token, bank_company_id, environment = _alatau_live_session(
            company_id, environment
        )
        kbk_name = _alatau_dictionary_name(client, access_token, "KBK", kbk)
        knp_name = _alatau_dictionary_name(client, access_token, "KNP", knp)
        if not kbk_name:
            return jsonify({
                "success": False,
                "error": f"КБК {kbk} не найден в справочнике Alatau",
            }), 400

        description = purpose or ". ".join(
            value for value in (kbk_name, knp_name) if value
        )
        description = description[:480]

        tax = {
            "periodStart": period_start,
            "periodEnd": period_end,
        }
        if vin:
            tax["vin"] = vin
        if protocol_number:
            tax["protocolNumber"] = protocol_number

        payload = {
            "type": "TAX",
            "category": "DOMESTIC",
            "paymentRecipient": {
                "iinOrBin": "141040004756",
                "name": 'РГУ "Комитет государственных доходов Министерства финансов"',
                "recipientAccount": {
                    "iban": "KZ24070105KSN0000000",
                    "bankName": 'РГУ "Комитет казначейства Министерства финансов РК"',
                    "bic": "KKMFKZ2A",
                },
                "kbe": {
                    "code": "11",
                },
            },
            "details": {
                "knp": {
                    "code": knp,
                    "name": knp_name or None,
                },
                "kbk": {
                    "code": kbk,
                    "name": kbk_name,
                },
                "description": description,
                "tax": tax,
                "paymentAmount": {
                    "amount": amount,
                    "currency": "KZT",
                },
                "urgent": False,
                "payerIban": account_iban,
                "documentId": document_number,
                "factualSender": None,
            },
        }

        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        return jsonify({
            "success": True,
            "environment": environment,
            "company_id": bank_company_id,
            "payment_type": "TAX",
            "payload": payload,
            "resolved": {
                "kbkName": kbk_name,
                "knpName": knp_name,
                "purpose": description,
            },
            "signing_ts_ms": int(time.time() * 1000),
        })
    except AlatauError as exc:
        _alatau_touch(company_id, environment, error=str(exc)[:500])
        return jsonify({"success": False, "error": str(exc)}), exc.status_code


@settings_bp.route("/api/integrations/alatau/payments/draft", methods=["POST"])
def alatau_payment_draft():
    company_id, error = _alatau_current_company()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    environment = (data.get("environment") or "production").strip().lower()
    account_iban = (data.get("accountIban") or "").replace(" ", "").upper()
    receiver_name = (data.get("receiverName") or "").strip()
    receiver_iin_bin = (data.get("receiverIinBin") or "").strip()
    receiver_iban = (data.get("receiverIban") or "").replace(" ", "").upper()
    receiver_bic = (data.get("receiverBic") or "").replace(" ", "").upper()
    kbe = (data.get("kbe") or "").strip()
    knp = (data.get("knp") or "").strip()
    purpose = (data.get("purpose") or "").strip()
    document_number = (data.get("documentNumber") or "").strip()

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        amount = 0

    missing = []
    for field, value in (
        ("счёт списания", account_iban),
        ("получатель", receiver_name),
        ("БИН/ИИН", receiver_iin_bin),
        ("IBAN получателя", receiver_iban),
        ("БИК получателя", receiver_bic),
        ("КБЕ", kbe),
        ("КНП", knp),
        ("назначение платежа", purpose),
        ("номер документа", document_number),
    ):
        if not value:
            missing.append(field)
    if missing:
        return jsonify({
            "success": False,
            "error": "Заполните: " + ", ".join(missing),
        }), 400

    if amount <= 0:
        return jsonify({"success": False, "error": "Сумма должна быть больше 0"}), 400
    if len(receiver_iin_bin) not in (12,):
        return jsonify({"success": False, "error": "БИН/ИИН должен содержать 12 цифр"}), 400
    if not receiver_iin_bin.isdigit():
        return jsonify({"success": False, "error": "БИН/ИИН должен содержать только цифры"}), 400
    if len(kbe) != 2 or not kbe.isdigit():
        return jsonify({"success": False, "error": "КБЕ должен состоять из 2 цифр"}), 400
    if len(knp) != 3 or not knp.isdigit():
        return jsonify({"success": False, "error": "КНП должен состоять из 3 цифр"}), 400

    payment_type = "INTERNAL" if receiver_bic == "TSESKZKA" else "EXTERNAL"

    # Resolve the recipient bank name from Alatau's own bank dictionary.
    # Production validates recipientAccount.bankName as a required field.
    receiver_bank_name = receiver_bic
    try:
        lookup_client, lookup_token, lookup_company_id, _ = _alatau_live_session(
            company_id, environment
        )
        bank_rows = lookup_client.get_banks(lookup_token)
        if isinstance(bank_rows, dict):
            bank_rows = (
                bank_rows.get("content")
                or bank_rows.get("items")
                or bank_rows.get("data")
                or bank_rows.get("banks")
                or []
            )
        if isinstance(bank_rows, list):
            for bank in bank_rows:
                if not isinstance(bank, dict):
                    continue
                bic = str(
                    bank.get("bic")
                    or bank.get("bankBic")
                    or bank.get("code")
                    or ""
                ).replace(" ", "").upper()
                if bic == receiver_bic:
                    receiver_bank_name = str(
                        bank.get("name")
                        or bank.get("bankName")
                        or bank.get("fullName")
                        or receiver_bic
                    ).strip()
                    break
    except AlatauError:
        # The payment endpoint will still return a precise validation error if
        # the bank dictionary is temporarily unavailable.
        pass

    # Production requires the human-readable KBE name as well as its code.
    kbe_name = kbe
    try:
        kbe_rows = lookup_client.get_dictionary(lookup_token, "KBE")
        if isinstance(kbe_rows, dict):
            kbe_rows = (
                kbe_rows.get("content")
                or kbe_rows.get("items")
                or kbe_rows.get("data")
                or kbe_rows.get("values")
                or []
            )
        if isinstance(kbe_rows, list):
            for row in kbe_rows:
                if not isinstance(row, dict):
                    continue
                row_code = str(
                    row.get("code") or row.get("value") or row.get("id") or ""
                ).strip()
                if row_code == kbe:
                    kbe_name = str(
                        row.get("name")
                        or row.get("title")
                        or row.get("description")
                        or kbe
                    ).strip()
                    break
    except (AlatauError, UnboundLocalError):
        pass

    # Production also requires the human-readable KNP name.
    knp_name = knp
    try:
        knp_rows = lookup_client.get_dictionary(lookup_token, "KNP")
        if isinstance(knp_rows, dict):
            knp_rows = (
                knp_rows.get("content")
                or knp_rows.get("items")
                or knp_rows.get("data")
                or knp_rows.get("values")
                or []
            )
        if isinstance(knp_rows, list):
            for row in knp_rows:
                if not isinstance(row, dict):
                    continue
                row_code = str(
                    row.get("code") or row.get("value") or row.get("id") or ""
                ).strip()
                if row_code == knp:
                    knp_name = str(
                        row.get("name")
                        or row.get("title")
                        or row.get("description")
                        or knp
                    ).strip()
                    break
    except (AlatauError, UnboundLocalError):
        pass

    # Alatau v2 expects a nested payment model. Top-level aliases such as
    # paymentType/receiverIban are not part of the current Production schema.
    payload = {
        "type": payment_type,
        "category": "DOMESTIC",
        "paymentRecipient": {
            "iinOrBin": receiver_iin_bin,
            "name": receiver_name,
            "kbe": {
                "code": kbe,
                "name": kbe_name,
            },
            "recipientAccount": {
                "iban": receiver_iban,
                "bic": receiver_bic,
                "bankName": receiver_bank_name,
            },
        },
        "details": {
            "associatedField": {
                "parameters": {
                    "signatureNoCommission": False,
                    "paymentPurpose": purpose,
                },
            },
            "knp": {
                "code": knp,
                "name": knp_name,
            },
            "description": purpose,
            "payerIban": account_iban,
            "paymentAmount": {
                "amount": round(amount, 2),
                "currency": "KZT",
            },
            "vat": False,
            "urgent": False,
            "documentId": document_number,
            "permitRecord": False,
            "paymentPurpose": purpose,
        },
    }

    if data.get("prepareOnly") is True:
        return jsonify({
            "success": True,
            "environment": environment,
            "payment_type": payment_type,
            "payload": payload,
            # The bank validates the JWS header timestamp against its current
            # banking date. Use server time so a wrong phone clock/timezone
            # cannot make an otherwise valid signature look stale.
            "signing_ts_ms": int(time.time() * 1000),
        })

    try:
        client, access_token, bank_company_id, environment = _alatau_live_session(
            company_id, environment
        )
        result = client.create_contractor_draft(
            access_token,
            bank_company_id,
            payload,
        )
        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        _alatau_store_payment(
            company_id,
            environment,
            {
                "paymentType": payment_type,
                "accountIban": account_iban,
                "receiverName": receiver_name,
                "receiverIinBin": receiver_iin_bin,
                "receiverIban": receiver_iban,
                "receiverBic": receiver_bic,
                "kbe": kbe,
                "knp": knp,
                "amount": amount,
                "documentNumber": document_number,
                "purpose": purpose,
            },
            result,
            fallback_status="READY_TO_SEND",
            fallback_message="Черновик создан в Alatau",
        )
        return jsonify({
            "success": True,
            "environment": environment,
            "company_id": bank_company_id,
            "payment_type": payment_type,
            "draft": result,
        })
    except AlatauError as exc:
        _alatau_touch(company_id, environment, error=str(exc)[:500])
        return jsonify({"success": False, "error": str(exc)}), exc.status_code


def _alatau_jws_debug(content):
    """Return non-secret metadata from a compact JWS for diagnostics."""
    value = (content or "").strip()
    parts = value.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("Модуль подписи передал некорректный compact JWS")

    def decode_segment(segment):
        padded = segment + ("=" * ((4 - len(segment) % 4) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    try:
        protected = json.loads(decode_segment(parts[0]).decode("utf-8"))
        signature_bytes = decode_segment(parts[2])
    except Exception as exc:
        raise ValueError("Не удалось разобрать JWS, сформированный модулем подписи") from exc

    ts_raw = protected.get("ts") if isinstance(protected, dict) else None
    try:
        ts_ms = int(str(ts_raw))
    except (TypeError, ValueError):
        ts_ms = None

    now_ms = int(time.time() * 1000)
    delta_seconds = (
        round((now_ms - ts_ms) / 1000.0, 3)
        if ts_ms is not None
        else None
    )
    x5c = protected.get("x5c") if isinstance(protected, dict) else None
    return {
        "alg": protected.get("alg") if isinstance(protected, dict) else None,
        "typ": protected.get("typ") if isinstance(protected, dict) else None,
        "cty": protected.get("cty") if isinstance(protected, dict) else None,
        "ts": str(ts_raw) if ts_raw is not None else None,
        "delta_seconds": delta_seconds,
        "signature_bytes": len(signature_bytes),
        "x5c_count": len(x5c) if isinstance(x5c, list) else 0,
        "payload_bytes": len(decode_segment(parts[1])),
    }


@settings_bp.route("/api/integrations/alatau/payments/signed", methods=["POST"])
def alatau_signed_payment():
    company_id, error = _alatau_current_company()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    environment = (data.get("environment") or "production").strip().lower()
    content = (data.get("content") or "").strip()
    payment_meta = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    if environment != "production":
        return jsonify({"success": False, "error": "Подписанные платежи разрешены только в Production"}), 400
    if not content:
        return jsonify({"success": False, "error": "Модуль подписи не передал JWS"}), 400

    try:
        signature_debug = _alatau_jws_debug(content)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    # The bank's own NCALayer instruction explicitly requires the compact
    # [header].[payload].[signature] JWS string in POST /signed-payments.
    # Reject a stale timestamp locally so a bank-side "dated today" error
    # cannot be caused by Nika's clock handling.
    delta_seconds = signature_debug.get("delta_seconds")
    if delta_seconds is None or abs(delta_seconds) > 300:
        return jsonify({
            "success": False,
            "error": (
                "Временная метка JWS некорректна или устарела. "
                "Подпишите платёж заново."
            ),
            "signature_debug": signature_debug,
        }), 400

    logger.warning(
        "Alatau signed payment JWS meta company_id=%s meta=%s",
        company_id,
        signature_debug,
    )

    try:
        client, access_token, bank_company_id, environment = _alatau_live_session(
            company_id, environment
        )
        result = client.send_signed_payment(
            access_token,
            bank_company_id,
            content,
        )
        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        _alatau_store_payment(
            company_id,
            environment,
            payment_meta,
            result,
            fallback_status="SENT",
            fallback_message="Платёж подписан и передан в Alatau",
        )
        return jsonify({
            "success": True,
            "environment": environment,
            "company_id": bank_company_id,
            "payment": result,
        })
    except AlatauError as exc:
        logger.warning(
            "Alatau signed payment rejected company_id=%s status=%s meta=%s error=%s",
            company_id,
            exc.status_code,
            signature_debug,
            str(exc),
        )
        _alatau_touch(company_id, environment, error=str(exc)[:500])
        _alatau_store_payment(
            company_id,
            environment,
            payment_meta,
            None,
            fallback_status="ERROR",
            fallback_message=str(exc),
        )
        return jsonify({
            "success": False,
            "error": str(exc),
            "signature_debug": signature_debug,
        }), exc.status_code


@settings_bp.route("/api/integrations/alatau/payments/history")
def alatau_payment_history():
    company_id, error = _alatau_current_company()
    if error:
        return error

    environment = (request.args.get("environment") or "production").strip().lower()
    refresh = (request.args.get("refresh") or "").strip().lower() in ("1", "true", "yes")
    refresh_warning = None

    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_alatau_payment_history_table(cur)
        conn.commit()

        if refresh:
            try:
                client, access_token, bank_company_id, environment = _alatau_live_session(
                    company_id, environment
                )
                cur.execute("""
                    SELECT id, operation_id
                    FROM alatau_payment_history
                    WHERE company_id = %s
                      AND environment = %s
                      AND operation_id IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 40
                """, (company_id, environment))
                rows_to_refresh = cur.fetchall() or []

                for payment_row in rows_to_refresh:
                    row = dict(payment_row) if not isinstance(payment_row, dict) else payment_row
                    operation_id = row.get("operation_id")
                    if not operation_id:
                        continue
                    try:
                        status_payload = client.get_payment_status(
                            access_token, bank_company_id, operation_id
                        )
                        status_obj = (
                            status_payload.get("status")
                            if isinstance(status_payload, dict)
                            else None
                        )
                        if isinstance(status_obj, dict):
                            status_code = str(status_obj.get("code") or "UNKNOWN")
                            status_message = str(status_obj.get("message") or "")
                            status_timestamp = status_obj.get("timestamp")
                        else:
                            status_code = str(status_obj or "UNKNOWN")
                            status_message = ""
                            status_timestamp = None
                        cur.execute("""
                            UPDATE alatau_payment_history
                            SET status_code = %s,
                                status_message = %s,
                                bank_status_timestamp = COALESCE(%s, bank_status_timestamp),
                                updated_at = NOW()
                            WHERE id = %s
                        """, (
                            status_code[:120],
                            status_message[:500] or None,
                            status_timestamp or None,
                            row.get("id"),
                        ))
                    except AlatauError as status_exc:
                        if status_exc.status_code not in (400, 404):
                            refresh_warning = str(status_exc)
                conn.commit()
            except AlatauError as exc:
                refresh_warning = str(exc)

        cur.execute("""
            SELECT id, operation_id, payment_type, payer_iban,
                   receiver_name, receiver_iin_bin, receiver_iban, receiver_bic,
                   kbe, knp, kbk, period_start, period_end, amount, currency,
                   document_number, purpose,
                   status_code, status_message, bank_status_timestamp,
                   created_at, updated_at
            FROM alatau_payment_history
            WHERE company_id = %s AND environment = %s
            ORDER BY created_at DESC
            LIMIT 100
        """, (company_id, environment))
        rows = cur.fetchall() or []

        payments = []
        for item in rows:
            row = dict(item) if not isinstance(item, dict) else item
            payments.append({
                "id": row.get("id"),
                "operationId": row.get("operation_id"),
                "paymentType": row.get("payment_type"),
                "payerIban": row.get("payer_iban"),
                "receiverName": row.get("receiver_name"),
                "receiverIinBin": row.get("receiver_iin_bin"),
                "receiverIban": row.get("receiver_iban"),
                "receiverBic": row.get("receiver_bic"),
                "kbe": row.get("kbe"),
                "knp": row.get("knp"),
                "kbk": row.get("kbk"),
                "periodStart": row.get("period_start"),
                "periodEnd": row.get("period_end"),
                "amount": float(row.get("amount")) if row.get("amount") is not None else None,
                "currency": row.get("currency") or "KZT",
                "documentNumber": row.get("document_number"),
                "purpose": row.get("purpose"),
                "statusCode": row.get("status_code"),
                "statusMessage": row.get("status_message"),
                "bankStatusTimestamp": row.get("bank_status_timestamp").isoformat()
                    if row.get("bank_status_timestamp") else None,
                "createdAt": row.get("created_at").isoformat()
                    if row.get("created_at") else None,
                "updatedAt": row.get("updated_at").isoformat()
                    if row.get("updated_at") else None,
            })

        return jsonify({
            "success": True,
            "environment": environment,
            "payments": payments,
            "refresh_warning": refresh_warning,
        })
    finally:
        pool.putconn(conn)



def _ensure_bank_statement_links_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_statement_links (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            environment TEXT NOT NULL DEFAULT 'production',
            operation_key TEXT NOT NULL,
            account_iban TEXT,
            operation_date DATE,
            direction TEXT,
            amount NUMERIC(14, 2),
            currency TEXT,
            counterparty_name TEXT,
            counterparty_iin_bin TEXT,
            purpose TEXT,
            link_type TEXT NOT NULL,
            link_id BIGINT NOT NULL,
            link_label TEXT,
            created_by INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bank_statement_links_operation
        ON bank_statement_links(company_id, environment, operation_key)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bank_statement_links_company
        ON bank_statement_links(company_id, environment, updated_at DESC)
    """)


def _statement_rows(statement):
    if isinstance(statement, list):
        return [row for row in statement if isinstance(row, dict)]
    if not isinstance(statement, dict):
        return []

    for key in ("transactions", "operations", "items", "data", "entries", "documents"):
        nested = statement.get(key)
        if isinstance(nested, list):
            return [row for row in nested if isinstance(row, dict)]
        if isinstance(nested, dict):
            items = nested.get("items")
            if isinstance(items, list):
                return [row for row in items if isinstance(row, dict)]
    return []


def _statement_first(source, keys, default=""):
    if not isinstance(source, dict):
        return default
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _statement_number(value):
    if isinstance(value, dict):
        value = _statement_first(value, ("amount", "value", "sum", "balance"), 0)
    if isinstance(value, (int, float)):
        return abs(float(value))
    text = str(value or "").replace("\u00a0", "").replace(" ", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    try:
        return abs(float(text))
    except (TypeError, ValueError):
        return 0.0


def _statement_date_value(value):
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text[:10]]
    if "." in text[:10]:
        parts = text[:10].split(".")
        if len(parts) == 3:
            candidates.append(f"{parts[2]}-{parts[1]}-{parts[0]}")
    for candidate in candidates:
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _statement_normalize_name(value):
    return re.sub(r"[^a-zа-яё0-9]+", "", str(value or "").lower(), flags=re.IGNORECASE)


def _statement_nested_counterparty(row):
    name = str(_statement_first(
        row,
        (
            "counterpartyName", "partnerName", "recipientName", "senderName",
            "beneficiaryName", "payerName", "receiverName", "customerName",
        ),
        "",
    ) or "").strip()
    iin_bin = re.sub(r"\D", "", str(_statement_first(
        row,
        (
            "counterpartyIinBin", "counterpartyBin", "counterpartyIin",
            "iinBin", "iinOrBin", "payerIin", "payerBin", "senderIin",
            "senderBin", "recipientIin", "recipientBin", "beneficiaryIin",
            "beneficiaryBin",
        ),
        "",
    ) or ""))

    if name and iin_bin:
        return name, iin_bin

    for key in (
        "counterparty", "partner", "payer", "sender", "recipient",
        "beneficiary", "paymentRecipient", "customer",
    ):
        nested = row.get(key)
        if not isinstance(nested, dict):
            continue
        if not name:
            name = str(_statement_first(
                nested,
                ("name", "fullName", "companyName", "title"),
                "",
            ) or "").strip()
        if not iin_bin:
            iin_bin = re.sub(r"\D", "", str(_statement_first(
                nested,
                ("iinBin", "iinOrBin", "bin", "iin", "identifier"),
                "",
            ) or ""))
        if name and iin_bin:
            break
    return name, iin_bin


def _normalize_statement_operation(row, iban):
    direct_debit = _statement_number(_statement_first(
        row, ("debit", "debitAmount", "outcome", "expense"), 0
    ))
    direct_credit = _statement_number(_statement_first(
        row, ("credit", "creditAmount", "income"), 0
    ))
    generic_amount = _statement_number(_statement_first(
        row, ("amount", "sum", "operationAmount", "paymentAmount"), 0
    ))
    operation_type = str(_statement_first(
        row, ("operationType", "type", "direction"), ""
    ) or "").upper()

    if direct_debit > 0:
        direction = "debit"
        amount = direct_debit
    elif direct_credit > 0:
        direction = "credit"
        amount = direct_credit
    elif operation_type in ("DEBIT", "OUT", "OUTGOING", "EXPENSE"):
        direction = "debit"
        amount = generic_amount
    elif operation_type in ("CREDIT", "IN", "INCOMING", "INCOME"):
        direction = "credit"
        amount = generic_amount
    else:
        direction = "unknown"
        amount = generic_amount

    date_raw = _statement_first(
        row,
        ("operDate", "date", "operationDate", "transactionDate", "valueDate", "createdAt"),
        "",
    )
    operation_date = _statement_date_value(date_raw)
    document_number = str(_statement_first(
        row, ("documentNumber", "number", "reference", "documentId"), ""
    ) or "").strip()
    external_id = str(_statement_first(
        row, ("operationId", "transactionId", "id", "reference"), ""
    ) or "").strip()
    counterparty_name, counterparty_iin_bin = _statement_nested_counterparty(row)
    purpose = str(_statement_first(
        row, ("purpose", "paymentPurpose", "description", "details"), ""
    ) or "").strip()
    if isinstance(row.get("details"), dict):
        details = row.get("details")
        if not purpose or purpose.startswith("{"):
            purpose = str(_statement_first(
                details, ("paymentPurpose", "description", "purpose"), ""
            ) or "").strip()

    currency = str(_statement_first(
        row, ("currency", "currencyCode"), ""
    ) or "").strip().upper()
    for amount_key in ("amount", "sum", "operationAmount", "paymentAmount", "debitAmount", "creditAmount"):
        amount_obj = row.get(amount_key)
        if isinstance(amount_obj, dict):
            currency = str(_statement_first(
                amount_obj, ("currency", "currencyCode"), currency or "KZT"
            ) or "KZT").strip().upper()
            break
    if not currency:
        currency = "KZT"

    seed = "|".join([
        str(iban or "").upper(),
        external_id,
        operation_date.isoformat() if operation_date else str(date_raw or ""),
        document_number,
        direction,
        f"{amount:.2f}",
        counterparty_iin_bin,
        counterparty_name,
        purpose,
    ])
    operation_key = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]

    return {
        "operationKey": operation_key,
        "externalId": external_id,
        "date": operation_date.isoformat() if operation_date else str(date_raw or ""),
        "documentNumber": document_number,
        "counterpartyName": counterparty_name,
        "counterpartyIinBin": counterparty_iin_bin,
        "purpose": purpose,
        "direction": direction,
        "amount": round(amount, 2),
        "currency": currency,
        "raw": row,
    }


def _statement_suggestions(company_id, environment, operations, date_from_value, date_to_value):
    if not operations:
        return operations

    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_bank_statement_links_table(cur)
        conn.commit()

        cur.execute("""
            SELECT operation_key, link_type, link_id, link_label, updated_at
            FROM bank_statement_links
            WHERE company_id = %s AND environment = %s
            ORDER BY updated_at DESC
            LIMIT 1000
        """, (company_id, environment))
        links = {}
        for row in cur.fetchall() or []:
            item = dict(row) if not isinstance(row, dict) else row
            links[item["operation_key"]] = {
                "type": item.get("link_type"),
                "id": item.get("link_id"),
                "label": item.get("link_label") or "",
                "linked": True,
            }

        cur.execute("""
            SELECT id, name, bin_iin, iban
            FROM suppliers
            WHERE company_id = %s AND COALESCE(is_active, TRUE) = TRUE
            ORDER BY id DESC
            LIMIT 1000
        """, (company_id,))
        suppliers = [
            dict(row) if not isinstance(row, dict) else row
            for row in (cur.fetchall() or [])
        ]

        cur.execute("""
            SELECT id, full_name, company_name, iin
            FROM clients
            WHERE company_id = %s AND COALESCE(is_deleted, FALSE) = FALSE
            ORDER BY id DESC
            LIMIT 2000
        """, (company_id,))
        clients = [
            dict(row) if not isinstance(row, dict) else row
            for row in (cur.fetchall() or [])
        ]

        range_from = date_from_value - timedelta(days=3)
        range_to = date_to_value + timedelta(days=3)
        cur.execute("""
            SELECT s.id, s.sale_number, s.total_amount, s.created_at,
                   c.id AS client_id, c.full_name, c.company_name, c.iin
            FROM sales s
            LEFT JOIN clients c ON c.id = s.client_id
            WHERE s.company_id = %s
              AND DATE(s.created_at) BETWEEN %s AND %s
              AND COALESCE(s.is_refunded, FALSE) = FALSE
            ORDER BY s.created_at DESC
            LIMIT 1500
        """, (company_id, range_from, range_to))
        sales = [
            dict(row) if not isinstance(row, dict) else row
            for row in (cur.fetchall() or [])
        ]

        cur.execute("""
            SELECT id, category, description, amount, date, source_type, source_id
            FROM expenses
            WHERE company_id = %s
              AND date BETWEEN %s AND %s
            ORDER BY date DESC, id DESC
            LIMIT 1500
        """, (company_id, range_from, range_to))
        expenses = [
            dict(row) if not isinstance(row, dict) else row
            for row in (cur.fetchall() or [])
        ]

        for operation in operations:
            operation["link"] = links.get(operation["operationKey"])
            if operation["link"]:
                operation["suggestions"] = []
                continue

            direction = operation.get("direction")
            amount = float(operation.get("amount") or 0)
            op_date = _statement_date_value(operation.get("date"))
            cp_name = str(operation.get("counterpartyName") or "").strip()
            cp_norm = _statement_normalize_name(cp_name)
            cp_iin = re.sub(r"\D", "", str(operation.get("counterpartyIinBin") or ""))
            purpose_norm = _statement_normalize_name(operation.get("purpose"))
            suggestions = []

            def add_suggestion(kind, entity_id, label, score, reason, subtitle=""):
                if not entity_id or score < 70:
                    return
                suggestions.append({
                    "type": kind,
                    "id": entity_id,
                    "label": label or f"{kind} #{entity_id}",
                    "subtitle": subtitle,
                    "score": min(int(score), 100),
                    "reason": reason,
                })

            if direction == "debit":
                for supplier in suppliers:
                    score = 0
                    reasons = []
                    supplier_iin = re.sub(r"\D", "", str(supplier.get("bin_iin") or ""))
                    supplier_norm = _statement_normalize_name(supplier.get("name"))
                    if cp_iin and supplier_iin and cp_iin == supplier_iin:
                        score = 100
                        reasons.append("совпадает БИН/ИИН")
                    elif cp_norm and supplier_norm:
                        if cp_norm == supplier_norm:
                            score = 94
                            reasons.append("совпадает название")
                        elif len(cp_norm) >= 5 and (cp_norm in supplier_norm or supplier_norm in cp_norm):
                            score = 84
                            reasons.append("похоже название")
                    if score:
                        add_suggestion(
                            "supplier",
                            supplier.get("id"),
                            supplier.get("name"),
                            score,
                            ", ".join(reasons),
                            supplier.get("bin_iin") or "",
                        )

                for expense in expenses:
                    expense_amount = float(expense.get("amount") or 0)
                    if abs(expense_amount - amount) > 0.01:
                        continue
                    expense_date = expense.get("date")
                    date_score = 0
                    if op_date and expense_date:
                        try:
                            date_score = max(0, 12 - abs((op_date - expense_date).days) * 4)
                        except TypeError:
                            date_score = 0
                    desc_norm = _statement_normalize_name(expense.get("description"))
                    text_score = 0
                    if cp_norm and desc_norm and (cp_norm in desc_norm or desc_norm in cp_norm):
                        text_score = 10
                    elif purpose_norm and desc_norm and len(desc_norm) >= 5 and desc_norm in purpose_norm:
                        text_score = 8
                    score = 72 + date_score + text_score
                    add_suggestion(
                        "expense",
                        expense.get("id"),
                        expense.get("description"),
                        score,
                        "совпадает сумма" + (", близкая дата" if date_score else ""),
                        expense.get("category") or "",
                    )

            elif direction == "credit":
                matching_client_ids = set()
                for client in clients:
                    score = 0
                    reasons = []
                    client_iin = re.sub(r"\D", "", str(client.get("iin") or ""))
                    names = [
                        str(client.get("company_name") or "").strip(),
                        str(client.get("full_name") or "").strip(),
                    ]
                    if cp_iin and client_iin and cp_iin == client_iin:
                        score = 100
                        reasons.append("совпадает БИН/ИИН")
                    else:
                        for name in names:
                            norm = _statement_normalize_name(name)
                            if cp_norm and norm:
                                if cp_norm == norm:
                                    score = max(score, 94)
                                    reasons = ["совпадает имя/компания"]
                                elif len(cp_norm) >= 5 and (cp_norm in norm or norm in cp_norm):
                                    score = max(score, 84)
                                    reasons = ["похоже имя/компания"]
                    if score:
                        matching_client_ids.add(client.get("id"))
                        label = client.get("company_name") or client.get("full_name")
                        add_suggestion(
                            "client",
                            client.get("id"),
                            label,
                            score,
                            ", ".join(reasons),
                            client.get("iin") or "",
                        )

                for sale in sales:
                    sale_amount = float(sale.get("total_amount") or 0)
                    if abs(sale_amount - amount) > 0.01:
                        continue
                    created_at = sale.get("created_at")
                    sale_date = created_at.date() if hasattr(created_at, "date") else None
                    date_score = 0
                    if op_date and sale_date:
                        date_score = max(0, 14 - abs((op_date - sale_date).days) * 4)
                    client_bonus = 12 if sale.get("client_id") in matching_client_ids else 0
                    score = 70 + date_score + client_bonus
                    label_name = sale.get("company_name") or sale.get("full_name") or "Продажа"
                    add_suggestion(
                        "sale",
                        sale.get("id"),
                        f"{label_name} · Продажа №{sale.get('sale_number') or sale.get('id')}",
                        score,
                        "совпадает сумма" + (", клиент" if client_bonus else ""),
                        f"{sale_amount:.2f} KZT",
                    )

            suggestions.sort(key=lambda item: (-item["score"], item["type"], str(item["label"])))
            deduped = []
            seen = set()
            for suggestion in suggestions:
                key = (suggestion["type"], suggestion["id"])
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(suggestion)
                if len(deduped) >= 5:
                    break
            operation["suggestions"] = deduped

        return operations
    finally:
        pool.putconn(conn)


def _bank_link_entity(cur, company_id, link_type, link_id):
    if link_type == "supplier":
        cur.execute("""
            SELECT id, name
            FROM suppliers
            WHERE id = %s AND company_id = %s AND COALESCE(is_active, TRUE) = TRUE
        """, (link_id, company_id))
        row = cur.fetchone()
        return row, (row.get("name") if row else None)

    if link_type == "client":
        cur.execute("""
            SELECT id, full_name, company_name
            FROM clients
            WHERE id = %s AND company_id = %s AND COALESCE(is_deleted, FALSE) = FALSE
        """, (link_id, company_id))
        row = cur.fetchone()
        label = (row.get("company_name") or row.get("full_name")) if row else None
        return row, label

    if link_type == "sale":
        cur.execute("""
            SELECT s.id, s.sale_number, c.full_name, c.company_name
            FROM sales s
            LEFT JOIN clients c ON c.id = s.client_id
            WHERE s.id = %s AND s.company_id = %s
        """, (link_id, company_id))
        row = cur.fetchone()
        if not row:
            return None, None
        client_name = row.get("company_name") or row.get("full_name") or "Продажа"
        return row, f"{client_name} · Продажа №{row.get('sale_number') or row.get('id')}"

    if link_type == "expense":
        cur.execute("""
            SELECT id, category, description
            FROM expenses
            WHERE id = %s AND company_id = %s
        """, (link_id, company_id))
        row = cur.fetchone()
        label = row.get("description") if row else None
        return row, label

    return None, None


@settings_bp.route("/api/integrations/alatau/statements")
def alatau_statements():
    company_id, error = _alatau_current_company()
    if error:
        return error

    environment = (request.args.get("environment") or "test").strip().lower()
    iban = (request.args.get("iban") or "").strip().upper()
    date_to_text = request.args.get("date_to") or date.today().isoformat()
    date_from_text = request.args.get("date_from") or (
        date.today() - timedelta(days=30)
    ).isoformat()

    if not re.fullmatch(r"KZ[A-Z0-9]{18}", iban):
        return jsonify({"success": False, "error": "Неверный IBAN"}), 400

    try:
        date_from_value = date.fromisoformat(date_from_text)
        date_to_value = date.fromisoformat(date_to_text)
    except ValueError:
        return jsonify({"success": False, "error": "Неверный формат даты"}), 400

    if date_from_value > date_to_value:
        return jsonify({"success": False, "error": "Дата начала позже даты окончания"}), 400
    if (date_to_value - date_from_value).days > 92:
        return jsonify({
            "success": False,
            "error": "Alatau City Bank позволяет запрашивать выписку максимум за 92 дня",
        }), 400

    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 100, type=int), 1), 200)

    try:
        client, access_token, bank_company_id, environment = _alatau_live_session(
            company_id, environment
        )

        # Before requesting a statement, check the live account metadata.
        # Alatau returns accountType/status/openDate from the v1 accounts method.
        account = None
        try:
            accounts_payload = client.get_accounts(access_token, bank_company_id)
            if isinstance(accounts_payload, list):
                account_rows = accounts_payload
            elif isinstance(accounts_payload, dict):
                account_rows = (
                    accounts_payload.get("accounts")
                    or accounts_payload.get("data")
                    or accounts_payload.get("items")
                )
                if account_rows is None and accounts_payload.get("iban"):
                    account_rows = [accounts_payload]
                account_rows = account_rows or []
            else:
                account_rows = []

            account = next(
                (
                    row for row in account_rows
                    if str(row.get("iban") or "").strip().upper() == iban
                ),
                None,
            )
        except AlatauError:
            # The statement request below remains the source of truth if account
            # metadata cannot be loaded for some reason.
            account = None

        if account:
            account_type = str(account.get("accountType") or "").strip().upper()
            if account_type and account_type != "ACCOUNT":
                return jsonify({
                    "success": False,
                    "error": (
                        f"Выписка v3 недоступна для типа счёта {account_type}. "
                        "Alatau City Bank разрешает этот метод только для счетов ACCOUNT."
                    ),
                    "account": {
                        "iban": iban,
                        "accountType": account_type,
                        "status": account.get("status"),
                        "openDate": account.get("openDate"),
                    },
                }), 400

            open_date_text = str(account.get("openDate") or "").strip()
            if open_date_text:
                try:
                    open_date_value = date.fromisoformat(open_date_text[:10])
                except ValueError:
                    open_date_value = None
                if open_date_value and date_from_value < open_date_value:
                    return jsonify({
                        "success": False,
                        "code": "date_before_account_open",
                        "error": (
                            f"Счёт открыт {open_date_value.strftime('%d.%m.%Y')}. "
                            "Нельзя запрашивать выписку за период до даты открытия счёта."
                        ),
                        "open_date": open_date_value.isoformat(),
                        "account": {
                            "iban": iban,
                            "accountType": account.get("accountType"),
                            "status": account.get("status"),
                            "openDate": open_date_value.isoformat(),
                        },
                    }), 400

        effective_date_to = date_to_value
        statement = None
        fallback_date_to = None
        try:
            statement = client.get_statement(
                access_token,
                bank_company_id,
                iban,
                date_from_value.isoformat(),
                effective_date_to.isoformat(),
                page=page,
                page_size=page_size,
            )
        except AlatauError as statement_exc:
            if statement_exc.status_code != 412 or date_to_value < date.today():
                raise

            # The v3 specification defines dateTo by the operational banking
            # day. On a weekend (or before today's banking day is closed),
            # Alatau may reject "today" with HTTP 412. Retry the last weekday.
            fallback_date_to = date.today() - timedelta(days=1)
            while fallback_date_to.weekday() >= 5:
                fallback_date_to -= timedelta(days=1)

            if fallback_date_to < date_from_value:
                raise

            statement = client.get_statement(
                access_token,
                bank_company_id,
                iban,
                date_from_value.isoformat(),
                fallback_date_to.isoformat(),
                page=page,
                page_size=page_size,
            )
            effective_date_to = fallback_date_to
        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        response_payload = {
            "success": True,
            "environment": environment,
            "statement": statement,
            "requested_date_to": date_to_value.isoformat(),
            "effective_date_to": effective_date_to.isoformat(),
            "used_previous_banking_day": bool(fallback_date_to),
        }
        if request.args.get("smart", "").strip().lower() in ("1", "true", "yes"):
            operations = [
                _normalize_statement_operation(row, iban)
                for row in _statement_rows(statement)
            ]
            try:
                operations = _statement_suggestions(
                    company_id,
                    environment,
                    operations,
                    date_from_value,
                    date_to_value,
                )
            except Exception as smart_error:
                # The live bank statement remains usable even if the local
                # reconciliation layer has a temporary schema/data problem.
                for operation in operations:
                    operation["link"] = None
                    operation["suggestions"] = []
                response_payload["smart_warning"] = str(smart_error)
            response_payload["operations"] = operations

        return jsonify(response_payload)
    except AlatauError as exc:
        # HTTP 412 in Alatau is a generic "edge scenario" status. Do not replace
        # the bank's payload with a guessed cause: the response code/details are
        # much more useful for diagnosing the exact precondition that failed.
        error_message = str(exc)
        if exc.status_code == 412 and "HTTP 412" not in error_message:
            error_message = f"HTTP 412. {error_message}"
        _alatau_touch(company_id, environment, error=error_message[:500])
        return jsonify({
            "success": False,
            "error": error_message,
            "code": "alatau_statement_precondition" if exc.status_code == 412 else None,
        }), exc.status_code



@settings_bp.route("/api/integrations/alatau/statement-links", methods=["POST"])
def alatau_statement_link():
    company_id, error = _alatau_current_company()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    environment = str(data.get("environment") or "production").strip().lower()
    if environment not in ("test", "production"):
        return jsonify({"success": False, "error": "Неверный режим подключения"}), 400

    operation_key = str(data.get("operationKey") or "").strip()
    if not re.fullmatch(r"[a-f0-9]{40}", operation_key):
        return jsonify({"success": False, "error": "Некорректный идентификатор операции"}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_bank_statement_links_table(cur)

        if data.get("clear") is True:
            cur.execute("""
                DELETE FROM bank_statement_links
                WHERE company_id = %s AND environment = %s AND operation_key = %s
            """, (company_id, environment, operation_key))
            conn.commit()
            return jsonify({"success": True, "link": None})

        link_type = str(data.get("linkType") or "").strip().lower()
        if link_type not in ("supplier", "client", "sale", "expense"):
            return jsonify({"success": False, "error": "Неизвестный тип связи"}), 400
        try:
            link_id = int(data.get("linkId"))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Не выбран объект для связи"}), 400

        entity, label = _bank_link_entity(cur, company_id, link_type, link_id)
        if not entity:
            return jsonify({"success": False, "error": "Объект для связи не найден"}), 404

        operation_date = _statement_date_value(data.get("date"))
        amount = _statement_number(data.get("amount"))
        direction = str(data.get("direction") or "unknown").strip().lower()
        if direction not in ("debit", "credit", "unknown"):
            direction = "unknown"

        cur.execute("""
            INSERT INTO bank_statement_links (
                company_id, environment, operation_key, account_iban,
                operation_date, direction, amount, currency,
                counterparty_name, counterparty_iin_bin, purpose,
                link_type, link_id, link_label, created_by,
                created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                NOW(), NOW()
            )
            ON CONFLICT (company_id, environment, operation_key)
            DO UPDATE SET
                account_iban = EXCLUDED.account_iban,
                operation_date = EXCLUDED.operation_date,
                direction = EXCLUDED.direction,
                amount = EXCLUDED.amount,
                currency = EXCLUDED.currency,
                counterparty_name = EXCLUDED.counterparty_name,
                counterparty_iin_bin = EXCLUDED.counterparty_iin_bin,
                purpose = EXCLUDED.purpose,
                link_type = EXCLUDED.link_type,
                link_id = EXCLUDED.link_id,
                link_label = EXCLUDED.link_label,
                created_by = EXCLUDED.created_by,
                updated_at = NOW()
        """, (
            company_id,
            environment,
            operation_key,
            str(data.get("accountIban") or "").replace(" ", "").upper() or None,
            operation_date,
            direction,
            amount or None,
            str(data.get("currency") or "KZT").upper()[:8],
            str(data.get("counterpartyName") or "").strip()[:300] or None,
            re.sub(r"\D", "", str(data.get("counterpartyIinBin") or ""))[:12] or None,
            str(data.get("purpose") or "").strip()[:1000] or None,
            link_type,
            link_id,
            str(label or "")[:300],
            session.get("user_id"),
        ))
        conn.commit()
        return jsonify({
            "success": True,
            "link": {
                "type": link_type,
                "id": link_id,
                "label": label or "",
                "linked": True,
            },
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@settings_bp.route("/api/integrations/alatau/disconnect", methods=["POST"])
def alatau_disconnect():
    company_id, error = _alatau_current_company()
    if error:
        return error
    if not _alatau_valid_csrf():
        return jsonify({"success": False, "error": "Страница устарела. Обновите её"}), 403

    environment = (request.form.get("environment") or "production").strip().lower()
    if environment not in ("test", "production"):
        return jsonify({"success": False, "error": "Неверный режим подключения"}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_alatau_table(cur)
        cur.execute("""
            UPDATE alatau_integrations
            SET status = 'disconnected',
                client_id = NULL,
                client_secret_encrypted = NULL,
                access_token_encrypted = NULL,
                token_expires_at = NULL,
                bank_company_id = NULL,
                last_error = NULL,
                updated_at = NOW()
            WHERE company_id = %s AND environment = %s
        """, (company_id, environment))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
    return redirect("/settings/integrations/alatau?disconnected=1")


@settings_bp.route("/settings/kkm")
def kkm():
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("company_id"):
        return redirect("/dashboard")

    return render_template("settings/kkm.html")


@settings_bp.route("/settings/pos")
def pos():
    return render_template("settings/pos.html")


@settings_bp.route("/settings/catalog")
def catalog():
    return render_template("settings/catalog.html")


@settings_bp.route("/settings/backup")
def backup():
    return render_template("settings/backup.html")
    
@settings_bp.route("/settings/equipment")
def equipment():

    if not session.get("user_id"):
        return redirect("/login")

    return render_template("settings/equipment.html")
    
@settings_bp.route("/settings/printers")
def printers():
    return render_template("settings/printers.html")


@settings_bp.route("/settings/scanners")
def scanners():
    return render_template("settings/scanners.html")


@settings_bp.route("/settings/scales")
def scales():
    return render_template("settings/scales.html")
    
@settings_bp.route("/settings/rekassa")
def rekassa_settings():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = session.get("company_id")
    if not company_id:
        return redirect("/dashboard")

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                rekassa_enabled,
                rekassa_number,
                rekassa_crs_id,
                rekassa_serial_number
            FROM integrations
            WHERE company_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (company_id,))
        row = cur.fetchone()
        rekassa = dict(row) if row else {}
    finally:
        pool.putconn(conn)

    return render_template("rekassa_settings.html", rekassa=rekassa)
    
@settings_bp.route("/settings/whatsapp")
def whatsapp_settings():

    if not session.get("user_id"):
        return redirect("/login")

    company_id = session.get("company_id")

    if not company_id:
        return redirect("/dashboard")

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                phone,
                instance_id,
                enabled,
                ai_enabled,
                status,
                updated_at
            FROM whatsapp_integrations
            WHERE company_id = %s
            LIMIT 1
        """, (company_id,))

        whatsapp = cur.fetchone()

    finally:
        pool.putconn(conn)

    return render_template(
        "settings/whatsapp.html",
        whatsapp=whatsapp
    )
