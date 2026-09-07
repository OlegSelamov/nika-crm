import os
import secrets
from decimal import Decimal

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from models import get_db, pool
from subscriptions import get_company_subscription

subscriptions_bp = Blueprint("subscriptions", __name__)

BASE_MONTHLY_PRICE = Decimal("2990")
ANNUAL_MONTHS_CHARGED = Decimal("10")
EPAY_SCOPE = "webapi usermanagement email_send verification statement statistics payment"

# Public test merchant values are taken from Halyk ePay documentation.
# Production credentials must be supplied via environment variables.
EPAY_MODE = os.getenv("EPAY_MODE", "test").strip().lower()
EPAY_CLIENT_ID = os.getenv("EPAY_CLIENT_ID", "test")
EPAY_CLIENT_SECRET = os.getenv("EPAY_CLIENT_SECRET", "yF587AV9Ms94qN2QShFzVR3vFnWkhjbAK3sG")
EPAY_TERMINAL_ID = os.getenv("EPAY_TERMINAL_ID", "67e34d63-102f-4bd1-898e-370781d0074d")
EPAY_OAUTH_URL = (
    "https://epay-oauth.homebank.kz/oauth2/token"
    if EPAY_MODE == "prod"
    else "https://test-epay-oauth.epayment.kz/oauth2/token"
)
EPAY_STATUS_BASE_URL = (
    "https://epay-api.homebank.kz"
    if EPAY_MODE == "prod"
    else "https://test-epay-api.epayment.kz"
)
EPAY_PAYMENT_JS_URL = (
    "https://epay.homebank.kz/payform/payment-api.js"
    if EPAY_MODE == "prod"
    else "https://test-epay.epayment.kz/payform/payment-api.js"
)


def employee_price(employee_count):
    paid = max(int(employee_count or 0) - 1, 0)
    if paid <= 0:
        return Decimal("0")
    first_band = min(paid, 4) * Decimal("490")
    second_band = min(max(paid - 4, 0), 15) * Decimal("390")
    third_band = max(paid - 19, 0) * Decimal("290")
    return first_band + second_band + third_band


def calculate_total(modules, employee_count, billing_period):
    monthly_modules = sum((Decimal(str(m["monthly_price"] or 0)) for m in modules), Decimal("0"))
    monthly = BASE_MONTHLY_PRICE + monthly_modules + employee_price(employee_count)
    if billing_period == "year":
        return monthly, monthly * ANNUAL_MONTHS_CHARGED
    return monthly, monthly


def _ensure_epay_columns(cur):
    cur.execute("""
        ALTER TABLE subscription_payments
        ADD COLUMN IF NOT EXISTS provider_invoice_id TEXT
    """)
    cur.execute("""
        ALTER TABLE subscription_payments
        ADD COLUMN IF NOT EXISTS provider_secret_hash TEXT
    """)
    cur.execute("""
        ALTER TABLE subscription_payments
        ADD COLUMN IF NOT EXISTS provider_payload JSONB
    """)


def _public_base_url():
    configured = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return request.url_root.rstrip("/")


def _epay_token(extra=None):
    payload = {
        "grant_type": "client_credentials",
        "scope": EPAY_SCOPE,
        "client_id": EPAY_CLIENT_ID,
        "client_secret": EPAY_CLIENT_SECRET,
        "terminal": EPAY_TERMINAL_ID,
    }
    if extra:
        payload.update(extra)

    response = requests.post(EPAY_OAUTH_URL, data=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not data.get("access_token"):
        raise RuntimeError("Halyk ePay не вернул access_token")
    return data


def _check_epay_status(invoice_id):
    auth = _epay_token()
    response = requests.get(
        f"{EPAY_STATUS_BASE_URL}/check-status/payment/transaction/{invoice_id}",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def _mark_payment_paid(payment_id, status_payload):
    transaction = (status_payload or {}).get("transaction") or {}
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_epay_columns(cur)
        cur.execute("""
            SELECT sp.*, cs.billing_period
            FROM subscription_payments sp
            JOIN company_subscriptions cs ON cs.id = sp.subscription_id
            WHERE sp.id = %s
            FOR UPDATE
        """, (payment_id,))
        payment = cur.fetchone()
        if not payment:
            return False

        if payment["status"] == "paid":
            return True

        status_name = str(transaction.get("statusName") or "").upper()
        result_code = str((status_payload or {}).get("resultCode") or "")
        amount = Decimal(str(transaction.get("amount") or 0))
        expected = Decimal(str(payment["amount"] or 0))
        currency = str(transaction.get("currency") or "").upper()
        invoice_id = str(transaction.get("invoiceID") or transaction.get("invoiceId") or "")

        # Halyk status API returns AUTH for a successfully authorised/charged
        # test payment. resultCode=100 + reasonCode=0 is the successful result.
        reason_code = str(transaction.get("reasonCode") or "")
        if result_code != "100" or reason_code != "0" or status_name not in {"AUTH", "CHARGE"}:
            return False
        if amount != expected or currency != "KZT":
            return False
        if invoice_id and invoice_id != str(payment.get("provider_invoice_id") or ""):
            return False

        period_sql = "INTERVAL '1 year'" if payment["billing_period"] == "year" else "INTERVAL '1 month'"

        cur.execute("""
            UPDATE subscription_payments
            SET status = 'paid',
                provider_payment_id = %s,
                provider_payload = %s::jsonb,
                paid_at = NOW()
            WHERE id = %s
        """, (
            transaction.get("id"),
            __import__("json").dumps(status_payload, ensure_ascii=False),
            payment_id,
        ))

        cur.execute(f"""
            UPDATE company_subscriptions
            SET status = 'active',
                period_start = NOW(),
                period_end = NOW() + {period_sql},
                next_payment_at = NOW() + {period_sql},
                updated_at = NOW()
            WHERE id = %s
        """, (payment["subscription_id"],))

        cur.execute(f"""
            UPDATE company_modules
            SET status = 'active',
                activated_at = COALESCE(activated_at, NOW()),
                expires_at = NOW() + {period_sql},
                updated_at = NOW()
            WHERE company_id = %s
              AND enabled = TRUE
        """, (payment["company_id"],))

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _confirm_epay_payment(invoice_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_epay_columns(cur)
        cur.execute("""
            SELECT id
            FROM subscription_payments
            WHERE provider = 'halyk_epay'
              AND provider_invoice_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (str(invoice_id),))
        row = cur.fetchone()
        conn.commit()
    finally:
        cur.close()
        pool.putconn(conn)

    if not row:
        return False

    status_payload = _check_epay_status(invoice_id)
    return _mark_payment_paid(row["id"], status_payload)


@subscriptions_bp.route("/subscription", methods=["GET"])
def subscription():
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    company_id = session.get("company_id")
    if not company_id:
        return "Компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                m.*,
                COALESCE(cm.enabled, FALSE) AS selected,
                cm.status AS company_module_status
            FROM modules m
            LEFT JOIN company_modules cm
              ON cm.module_id = m.id
             AND cm.company_id = %s
            WHERE m.is_active = TRUE
            ORDER BY m.category, m.sort_order, m.id
        """, (company_id,))
        modules = cur.fetchall()

        cur.execute("SELECT COUNT(*) AS count FROM users WHERE company_id = %s", (company_id,))
        employee_count = cur.fetchone()["count"] or 0

        subscription_row = get_company_subscription(company_id)
        selected_modules = [m for m in modules if m["selected"]]
        monthly_total, annual_total = calculate_total(selected_modules, employee_count, "year")

        return render_template(
            "subscription.html",
            modules=modules,
            subscription=subscription_row,
            employee_count=employee_count,
            employee_total=employee_price(employee_count),
            base_price=BASE_MONTHLY_PRICE,
            monthly_total=monthly_total,
            annual_total=annual_total,
            required_module=request.args.get("required"),
            epay_mode=EPAY_MODE,
            paid=request.args.get("paid") == "1",
            payment_failed=request.args.get("payment_failed") == "1",
        )
    finally:
        cur.close()
        pool.putconn(conn)


@subscriptions_bp.route("/subscription/update", methods=["POST"])
def subscription_update():
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    is_owner = (
        session.get("role") == "owner"
        or session.get("is_creator")
        or session.get("is_super_admin")
    )

    if not is_owner:
        return "Только владелец компании может менять подписку", 403

    company_id = session.get("company_id")
    selected_codes = set(request.form.getlist("modules"))
    billing_period = request.form.get("billing_period", "month")
    if billing_period not in {"month", "year"}:
        billing_period = "month"

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM modules WHERE is_active = TRUE ORDER BY id")
        all_modules = cur.fetchall()
        selected_modules = [m for m in all_modules if m["code"] in selected_codes or m["is_core"]]

        cur.execute("SELECT COUNT(*) AS count FROM users WHERE company_id = %s", (company_id,))
        employee_count = cur.fetchone()["count"] or 0
        monthly_total, payable_total = calculate_total(selected_modules, employee_count, billing_period)

        cur.execute("""
            INSERT INTO company_subscriptions (
                company_id, status, billing_period, base_price,
                employees_price, modules_price, total_price,
                period_start, next_payment_at, auto_renew, updated_at
            )
            VALUES (
                %s, 'pending_payment', %s, %s,
                %s, %s, %s,
                NOW(), NOW(), FALSE, NOW()
            )
            ON CONFLICT (company_id)
            DO UPDATE SET
                status = 'pending_payment',
                billing_period = EXCLUDED.billing_period,
                base_price = EXCLUDED.base_price,
                employees_price = EXCLUDED.employees_price,
                modules_price = EXCLUDED.modules_price,
                total_price = EXCLUDED.total_price,
                updated_at = NOW()
        """, (
            company_id,
            billing_period,
            BASE_MONTHLY_PRICE,
            employee_price(employee_count),
            monthly_total - BASE_MONTHLY_PRICE - employee_price(employee_count),
            payable_total,
        ))

        selected_ids = {m["id"] for m in selected_modules}
        for module in all_modules:
            enabled = module["id"] in selected_ids
            cur.execute("""
                INSERT INTO company_modules (
                    company_id, module_id, enabled, status, price, billing_period, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (company_id, module_id)
                DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    status = EXCLUDED.status,
                    price = EXCLUDED.price,
                    billing_period = EXCLUDED.billing_period,
                    updated_at = NOW()
            """, (
                company_id,
                module["id"],
                enabled,
                "pending_payment" if enabled else "disabled",
                module["monthly_price"],
                billing_period,
            ))

        conn.commit()
        return redirect(url_for("subscriptions.epay_start"))
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


@subscriptions_bp.route("/subscription/payment/epay/start", methods=["GET"])
def epay_start():
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    is_owner = (
        session.get("role") == "owner"
        or session.get("is_creator")
        or session.get("is_super_admin")
    )
    if not is_owner:
        return "Только владелец компании может оплачивать подписку", 403

    company_id = session.get("company_id")
    subscription_row = get_company_subscription(company_id)
    if not subscription_row:
        return redirect(url_for("subscriptions.subscription"))

    amount = Decimal(str(subscription_row["total_price"] or 0))
    if amount <= 0:
        flash("Сумма подписки должна быть больше нуля.", "error")
        return redirect(url_for("subscriptions.subscription"))

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_epay_columns(cur)
        secret_hash = secrets.token_urlsafe(24)
        cur.execute("""
            INSERT INTO subscription_payments (
                company_id, subscription_id, amount, currency, provider,
                payment_method, status, description, provider_secret_hash
            )
            VALUES (%s, %s, %s, 'KZT', 'halyk_epay',
                    'card', 'created', %s, %s)
            RETURNING id
        """, (
            company_id,
            subscription_row["id"],
            amount,
            "Подписка Nika Business",
            secret_hash,
        ))
        payment_id = cur.fetchone()["id"]

        # Halyk ePay requires a unique invoiceID. The public test merchant is
        # shared, so sequential values like 000010 can already be occupied.
        invoice_id = None
        for _ in range(20):
            candidate = str(secrets.randbelow(900000) + 100000)
            cur.execute("""
                SELECT 1
                FROM subscription_payments
                WHERE provider = 'halyk_epay'
                  AND provider_invoice_id = %s
                LIMIT 1
            """, (candidate,))
            if not cur.fetchone():
                invoice_id = candidate
                break

        if not invoice_id:
            raise RuntimeError("Не удалось сформировать уникальный invoiceID ePay")

        cur.execute("""
            UPDATE subscription_payments
            SET provider_invoice_id = %s
            WHERE id = %s
        """, (invoice_id, payment_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)

    base_url = _public_base_url()
    post_link = f"{base_url}/subscription/payment/epay/callback"
    failure_post_link = f"{base_url}/subscription/payment/epay/failure-callback"
    success_link = f"{base_url}/subscription/payment/epay/success?invoice={invoice_id}"
    failure_link = f"{base_url}/subscription/payment/epay/failure?invoice={invoice_id}"

    try:
        auth = _epay_token({
            "invoiceID": invoice_id,
            "secret_hash": secret_hash,
            "amount": str(amount),
            "currency": "KZT",
            "postLink": post_link,
            "failurePostLink": failure_post_link,
        })
    except Exception as exc:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE subscription_payments
                SET status = 'token_error', description = %s
                WHERE id = %s
            """, (f"Ошибка ePay: {exc}", payment_id))
            conn.commit()
        finally:
            cur.close()
            pool.putconn(conn)
        flash("Не удалось открыть ePay. Попробуйте ещё раз.", "error")
        return redirect(url_for("subscriptions.subscription"))

    payment_object = {
        "invoiceId": invoice_id,
        "backLink": success_link,
        "failureBackLink": failure_link,
        "autoBackLink": True,
        "postLink": post_link,
        "failurePostLink": failure_post_link,
        "language": "rus",
        "description": "Подписка Nika Business",
        "accountId": f"company-{company_id}",
        "terminal": EPAY_TERMINAL_ID,
        "amount": float(amount),
        "currency": "KZT",
        "auth": auth,
    }

    return render_template(
        "subscription_epay.html",
        payment_object=payment_object,
        epay_js_url=EPAY_PAYMENT_JS_URL,
        amount=amount,
        epay_mode=EPAY_MODE,
    )


@subscriptions_bp.route("/subscription/payment/epay/callback", methods=["POST"])
def epay_callback():
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    invoice_id = str(payload.get("invoiceId") or payload.get("invoiceID") or "").strip()
    if not invoice_id:
        return jsonify({"ok": False, "error": "missing invoiceId"}), 400

    # Do not trust the browser/postLink payload as proof of payment.
    # Locate our invoice, then independently verify the transaction through
    # Halyk's authenticated status API.
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_epay_columns(cur)
        cur.execute("""
            SELECT id
            FROM subscription_payments
            WHERE provider = 'halyk_epay'
              AND provider_invoice_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (invoice_id,))
        payment = cur.fetchone()
        conn.commit()
    finally:
        cur.close()
        pool.putconn(conn)

    if not payment:
        return jsonify({"ok": False, "error": "payment not found"}), 404

    try:
        confirmed = _confirm_epay_payment(invoice_id)
    except Exception:
        return jsonify({"ok": False, "error": "status verification failed"}), 502

    return jsonify({"ok": confirmed}), (200 if confirmed else 409)


@subscriptions_bp.route("/subscription/payment/epay/failure-callback", methods=["POST"])
def epay_failure_callback():
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    invoice_id = str(payload.get("invoiceId") or payload.get("invoiceID") or "")
    if invoice_id:
        conn = get_db()
        cur = conn.cursor()
        try:
            _ensure_epay_columns(cur)
            cur.execute("""
                UPDATE subscription_payments
                SET status = CASE WHEN status = 'paid' THEN status ELSE 'failed' END,
                    provider_payload = %s::jsonb
                WHERE provider = 'halyk_epay'
                  AND provider_invoice_id = %s
            """, (
                __import__("json").dumps(payload, ensure_ascii=False),
                invoice_id,
            ))
            conn.commit()
        finally:
            cur.close()
            pool.putconn(conn)
    return jsonify({"ok": True})


@subscriptions_bp.route("/subscription/payment/epay/success", methods=["GET"])
def epay_success():
    invoice_id = str(request.args.get("invoice") or "")
    if invoice_id:
        try:
            if _confirm_epay_payment(invoice_id):
                flash("Оплата подтверждена. Подписка Nika Business активирована.", "success")
                return redirect(url_for("subscriptions.subscription", paid=1))
        except Exception:
            pass

    flash("Платёж получен, но подтверждение ещё обрабатывается. Проверьте статус через несколько секунд.", "warning")
    return redirect(url_for("subscriptions.subscription"))


@subscriptions_bp.route("/subscription/payment/epay/failure", methods=["GET"])
def epay_failure():
    flash("Оплата не завершена. Подписка не была списана как оплаченная.", "error")
    return redirect(url_for("subscriptions.subscription", payment_failed=1))
