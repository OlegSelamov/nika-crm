import re
import secrets
from datetime import date, timedelta

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
            "endpoint": endpoint,
            "accounts": accounts,
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
        },
    }

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

        statement = client.get_statement(
            access_token,
            bank_company_id,
            iban,
            date_from_value.isoformat(),
            date_to_value.isoformat(),
            page=page,
            page_size=page_size,
        )
        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        return jsonify({
            "success": True,
            "environment": environment,
            "statement": statement,
        })
    except AlatauError as exc:
        error_message = str(exc)
        if exc.status_code == 412:
            error_message = (
                "Alatau City Bank вернул HTTP 412 — нарушение предусловий для выписки. "
                "По спецификации выписка v3 доступна только для счетов с типом ACCOUNT. "
                "Также проверьте, что у Production-приложения Business API включён доступ "
                "«Выгрузка выписки»; после изменения прав банк требует новые Client ID / Client Secret."
            )
        _alatau_touch(company_id, environment, error=error_message[:500])
        return jsonify({"success": False, "error": error_message}), exc.status_code


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
