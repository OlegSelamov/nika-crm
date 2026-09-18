import secrets

from flask import Blueprint, jsonify, render_template, request, session, redirect
from models import get_db, pool
from services.alatau_client import AlatauClient, AlatauError, AlatauSecretCipher

# Imported for startup side effects: installs stock quantity sync, duplicate
# identifier protection and stock consistency diagnostic endpoints.
import routes.stock_consistency  # noqa: F401

settings_bp = Blueprint("settings", __name__)


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
        DROP CONSTRAINT IF EXISTS alatau_integrations_company_id_key
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_alatau_integrations_company
        ON alatau_integrations(company_id)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_alatau_integrations_company_environment
        ON alatau_integrations(company_id, environment)
    """)


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
    }


@settings_bp.route("/settings")
def settings():

    if not session.get("user_id"):
        return redirect("/login")

    return render_template("settings.html")
    
@settings_bp.route("/settings/integrations")
def integrations():
    return render_template("settings/integrations.html")


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

        encrypted_secret = AlatauSecretCipher().encrypt(client_secret)

        conn = get_db()
        try:
            cur = conn.cursor()
            _ensure_alatau_table(cur)
            cur.execute("""
                INSERT INTO alatau_integrations (
                    company_id, environment, client_id, client_secret_encrypted,
                    bank_company_id, status, connected_at, last_checked_at,
                    last_error, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, 'connected', NOW(), NOW(), NULL, NOW()
                )
                ON CONFLICT (company_id, environment) DO UPDATE SET
                    environment = EXCLUDED.environment,
                    client_id = EXCLUDED.client_id,
                    client_secret_encrypted = COALESCE(
                        EXCLUDED.client_secret_encrypted,
                        alatau_integrations.client_secret_encrypted
                    ),
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
                str(exc)[:500],
            ))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            pool.putconn(conn)
        return jsonify({"success": False, "error": str(exc)}), exc.status_code


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
