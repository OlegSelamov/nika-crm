import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, redirect, render_template, request, session

from models import get_db, pool
from services.bcc_client import (
    BCCClient,
    BCCConfigurationError,
    BCCError,
    BCCTokenCipher,
    token_expiry,
)


bcc_bp = Blueprint("bcc", __name__)
IBAN_PATTERN = re.compile(r"^KZ[A-Z0-9]{18}$")
IDN_PATTERN = re.compile(r"^\d{12}$")


def _current_company(require_admin=True):
    if not session.get("user_id"):
        return None, (jsonify({"success": False, "error": "Требуется войти"}), 401)
    company_id = session.get("company_id")
    if not company_id:
        return None, (
            jsonify({"success": False, "error": "Организация не выбрана"}),
            403,
        )
    if require_admin and not (
        session.get("is_super_admin")
        or session.get("role") in ("owner", "admin")
    ):
        return None, (
            jsonify({"success": False, "error": "Доступ разрешён владельцу"}),
            403,
        )
    return company_id, None


def _csrf_token():
    token = session.get("bcc_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["bcc_csrf_token"] = token
    return token


def _valid_csrf():
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("bcc_csrf_token")
    return bool(supplied and expected and secrets.compare_digest(supplied, expected))


def _integration_row(company_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM bcc_integrations
            WHERE company_id = %s
            LIMIT 1
            """,
            (company_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        pool.putconn(conn)


def _company_row(company_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, bin FROM companies WHERE id = %s LIMIT 1",
            (company_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        pool.putconn(conn)


def _record_error(company_id, message, status="error"):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bcc_integrations (
                company_id, environment, status, last_error, updated_at
            ) VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (company_id) DO UPDATE SET
                environment = EXCLUDED.environment,
                status = EXCLUDED.status,
                last_error = EXCLUDED.last_error,
                updated_at = NOW()
            """,
            (
                company_id,
                (BCCClient.configuration_status()["environment"]),
                status,
                str(message)[:500],
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        pool.putconn(conn)


def _save_client_tokens(company_id, client_idn, payload):
    cipher = BCCTokenCipher()
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not access_token:
        raise BCCError("BCC не вернул access_token")

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bcc_integrations (
                company_id,
                environment,
                client_idn,
                access_token_encrypted,
                refresh_token_encrypted,
                token_type,
                token_expires_at,
                scope,
                status,
                connected_at,
                last_error,
                updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                'connected', NOW(), NULL, NOW()
            )
            ON CONFLICT (company_id) DO UPDATE SET
                environment = EXCLUDED.environment,
                client_idn = EXCLUDED.client_idn,
                access_token_encrypted = EXCLUDED.access_token_encrypted,
                refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
                token_type = EXCLUDED.token_type,
                token_expires_at = EXCLUDED.token_expires_at,
                scope = EXCLUDED.scope,
                status = 'connected',
                connected_at = NOW(),
                last_error = NULL,
                updated_at = NOW()
            """,
            (
                company_id,
                BCCClient.configuration_status()["environment"],
                client_idn,
                cipher.encrypt(access_token),
                cipher.encrypt(refresh_token),
                payload.get("token_type") or "bearer",
                token_expiry(payload),
                payload.get("scope"),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _client_token(company_id):
    integration = _integration_row(company_id)
    if not integration or integration.get("status") != "connected":
        raise BCCError("Сначала подключите счёт BCC", status_code=409)

    cipher = BCCTokenCipher()
    access_token = cipher.decrypt(integration.get("access_token_encrypted"))
    expires_at = integration.get("token_expires_at")
    now = datetime.now(timezone.utc)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at > now + timedelta(seconds=30):
        return access_token

    refresh_token = cipher.decrypt(integration.get("refresh_token_encrypted"))
    if not refresh_token:
        raise BCCError(
            "Срок подключения BCC истёк. Подключите банк повторно",
            status_code=401,
        )

    payload = BCCClient().refresh_client_token(refresh_token)
    if not payload.get("refresh_token"):
        payload["refresh_token"] = refresh_token
    _save_client_tokens(company_id, integration.get("client_idn"), payload)
    return payload["access_token"]


def _touch_sync(company_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE bcc_integrations
            SET last_sync_at = NOW(), last_error = NULL, updated_at = NOW()
            WHERE company_id = %s
            """,
            (company_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        pool.putconn(conn)


@bcc_bp.route("/settings/integrations/bcc")
def bcc_settings():
    company_id, error = _current_company()
    if error:
        if error[1] == 401:
            return redirect("/login")
        return redirect("/settings")

    company = _company_row(company_id)
    integration = _integration_row(company_id)
    safe_integration = None
    if integration:
        safe_integration = {
            "status": integration.get("status"),
            "environment": integration.get("environment"),
            "client_idn": integration.get("client_idn"),
            "connected_at": integration.get("connected_at"),
            "last_sync_at": integration.get("last_sync_at"),
            "last_error": integration.get("last_error"),
        }
    return render_template(
        "settings/bcc.html",
        company=company,
        bcc=safe_integration,
        bcc_config=BCCClient.configuration_status(),
        csrf_token=_csrf_token(),
    )


@bcc_bp.route("/api/integrations/bcc/connect", methods=["POST"])
def bcc_connect():
    company_id, error = _current_company()
    if error:
        return error
    if not _valid_csrf():
        return jsonify({"success": False, "error": "Страница устарела. Обновите её"}), 403

    company = _company_row(company_id)
    client_idn = re.sub(r"\D", "", str((company or {}).get("bin") or ""))
    if not IDN_PATTERN.fullmatch(client_idn):
        return redirect("/settings/integrations/bcc?error=bin")

    try:
        client = BCCClient()
        auth_url = client.generate_auth_url(client_idn)
        session["bcc_oauth_company_id"] = company_id
        session["bcc_oauth_client_idn"] = client_idn
        session["bcc_oauth_started_at"] = int(time.time())

        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO bcc_integrations (
                    company_id, environment, client_idn, status,
                    last_error, updated_at
                ) VALUES (%s, %s, %s, 'authorizing', NULL, NOW())
                ON CONFLICT (company_id) DO UPDATE SET
                    environment = EXCLUDED.environment,
                    client_idn = EXCLUDED.client_idn,
                    status = 'authorizing',
                    last_error = NULL,
                    updated_at = NOW()
                """,
                (company_id, client.environment, client_idn),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)
        return redirect(auth_url)
    except BCCError as exc:
        _record_error(company_id, str(exc))
        return redirect("/settings/integrations/bcc?error=connect")


@bcc_bp.route("/api/integrations/bcc/callback")
def bcc_callback():
    if not session.get("user_id"):
        return redirect("/login?next=/settings/integrations/bcc")

    company_id = session.get("bcc_oauth_company_id")
    started_at = session.get("bcc_oauth_started_at")
    if (
        not company_id
        or company_id != session.get("company_id")
        or not started_at
        or int(time.time()) - int(started_at) > 900
    ):
        return redirect("/settings/integrations/bcc?error=session")

    bank_error = request.args.get("error")
    code = request.args.get("code")
    if bank_error or not code:
        _record_error(company_id, request.args.get("error_description") or bank_error or "Авторизация отменена")
        return redirect("/settings/integrations/bcc?error=cancelled")

    try:
        payload = BCCClient().exchange_authorization_code(code)
        _save_client_tokens(
            company_id,
            session.get("bcc_oauth_client_idn"),
            payload,
        )
    except BCCError as exc:
        _record_error(company_id, str(exc))
        return redirect("/settings/integrations/bcc?error=token")
    finally:
        session.pop("bcc_oauth_company_id", None)
        session.pop("bcc_oauth_client_idn", None)
        session.pop("bcc_oauth_started_at", None)

    return redirect("/settings/integrations/bcc?connected=1")


@bcc_bp.route("/api/integrations/bcc/accounts")
def bcc_accounts():
    company_id, error = _current_company()
    if error:
        return error
    try:
        token = _client_token(company_id)
        accounts = BCCClient().get_accounts(token)
        _touch_sync(company_id)
        return jsonify({"success": True, "accounts": accounts})
    except BCCError as exc:
        _record_error(company_id, str(exc), status="connected")
        return jsonify({"success": False, "error": str(exc)}), exc.status_code


@bcc_bp.route("/api/integrations/bcc/statements")
def bcc_statements():
    company_id, error = _current_company()
    if error:
        return error

    iban = (request.args.get("iban") or "").strip().upper()
    currency = (request.args.get("currency") or "KZT").strip().upper()
    date_to_text = request.args.get("date_to") or date.today().isoformat()
    date_from_text = request.args.get("date_from") or (
        date.today() - timedelta(days=30)
    ).isoformat()
    try:
        date_from_value = date.fromisoformat(date_from_text)
        date_to_value = date.fromisoformat(date_to_text)
    except ValueError:
        return jsonify({"success": False, "error": "Неверный формат даты"}), 400

    if not IBAN_PATTERN.fullmatch(iban):
        return jsonify({"success": False, "error": "Неверный IBAN"}), 400
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return jsonify({"success": False, "error": "Неверная валюта"}), 400
    if date_from_value > date_to_value or (date_to_value - date_from_value).days > 366:
        return jsonify({"success": False, "error": "Период выписки должен быть от 1 до 366 дней"}), 400

    try:
        token = _client_token(company_id)
        statement = BCCClient().get_statement(
            token,
            iban,
            date_from_value.isoformat(),
            date_to_value.isoformat(),
            currency,
            offset=max(request.args.get("offset", 0, type=int), 0),
            limit=min(max(request.args.get("limit", 100, type=int), 1), 500),
        )
        _touch_sync(company_id)
        return jsonify({"success": True, "statement": statement})
    except BCCError as exc:
        _record_error(company_id, str(exc), status="connected")
        return jsonify({"success": False, "error": str(exc)}), exc.status_code


@bcc_bp.route("/api/integrations/bcc/disconnect", methods=["POST"])
def bcc_disconnect():
    company_id, error = _current_company()
    if error:
        return error
    if not _valid_csrf():
        return jsonify({"success": False, "error": "Страница устарела. Обновите её"}), 403

    integration = _integration_row(company_id)
    revoke_error = None
    if integration and integration.get("refresh_token_encrypted"):
        try:
            token = BCCTokenCipher().decrypt(
                integration.get("refresh_token_encrypted")
            )
            BCCClient().revoke_client_token(token)
        except BCCError as exc:
            revoke_error = str(exc)

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE bcc_integrations
            SET access_token_encrypted = NULL,
                refresh_token_encrypted = NULL,
                token_expires_at = NULL,
                status = 'disconnected',
                last_error = %s,
                updated_at = NOW()
            WHERE company_id = %s
            """,
            (revoke_error, company_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

    return redirect("/settings/integrations/bcc?disconnected=1")
