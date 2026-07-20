from decimal import Decimal
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from models import get_db, pool
from subscriptions import get_company_subscription

subscriptions_bp = Blueprint("subscriptions", __name__)

BASE_MONTHLY_PRICE = Decimal("2990")
ANNUAL_MONTHS_CHARGED = Decimal("10")


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
        )
    finally:
        cur.close()
        pool.putconn(conn)


@subscriptions_bp.route("/subscription/update", methods=["POST"])
def subscription_update():
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    if session.get("role") != "admin" and not session.get("is_super_admin") and not session.get("is_creator"):
        return "Только владелец компании может менять подписку", 403

    company_id = session.get("company_id")
    selected_codes = set(request.form.getlist("modules"))
    billing_period = request.form.get("billing_period", "month")

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
                "trial" if enabled else "disabled",
                module["monthly_price"],
                billing_period,
            ))

        conn.commit()
        flash("Состав подписки сохранён. Следующим этапом подключим онлайн-оплату.", "success")
        return redirect(url_for("subscriptions.subscription"))
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)
