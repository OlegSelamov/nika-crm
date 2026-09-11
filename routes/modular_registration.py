from decimal import Decimal

from flask import redirect, render_template, request, session, url_for

from models import get_db, pool
from routes.auth import (
    DEFAULT_REGISTRATION_PLAN,
    REGISTRATION_PLANS,
    load_user_module_codes,
    normalize_registration_plan,
)
from routes.onboarding import BUSINESS_PRESETS, ensure_onboarding_row
from utils.timezone import now_kz


REGISTRATION_BASE_PRICE = Decimal("2990")

PLAN_MODULE_PRESETS = {
    "start": {"sales", "catalog", "clients"},
    "business": {"sales", "analytics", "catalog", "warehouse", "suppliers", "clients"},
    "pro": {
        "sales", "analytics", "catalog", "storefront", "tasks", "accounting",
        "reports", "expenses", "warehouse", "suppliers", "clients",
    },
}


def ensure_supplier_subscription_module(cur):
    """Ensure the Suppliers add-on exists in the shared subscription catalog."""
    cur.execute("""
        INSERT INTO modules (
            code, name, description, category, monthly_price,
            route_prefix, icon, is_core, is_active, sort_order
        )
        VALUES (
            'suppliers', 'Поставщики',
            'База поставщиков, реквизиты контрагентов и связь с приходом товара.',
            'Склад', 490, '/suppliers', '/static/icons/company.png', FALSE, TRUE, 115
        )
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            category = EXCLUDED.category,
            monthly_price = EXCLUDED.monthly_price,
            route_prefix = EXCLUDED.route_prefix,
            icon = EXCLUDED.icon,
            is_core = EXCLUDED.is_core,
            is_active = TRUE,
            sort_order = EXCLUDED.sort_order
    """)


def _registration_modules(cur):
    ensure_supplier_subscription_module(cur)
    cur.execute("""
        SELECT id, code, name, description, category, monthly_price,
               route_prefix, icon, is_core, sort_order
        FROM modules
        WHERE is_active = TRUE
          AND code <> 'cto'
        ORDER BY category, sort_order, id
    """)
    return cur.fetchall()


def _default_codes(plan_code, modules):
    available = {m["code"] for m in modules}
    core = {m["code"] for m in modules if m["is_core"]}
    preset = PLAN_MODULE_PRESETS.get(plan_code, PLAN_MODULE_PRESETS[DEFAULT_REGISTRATION_PLAN])
    return core | (set(preset) & available)


def _selected_rows(modules, selected_codes):
    return [m for m in modules if m["is_core"] or m["code"] in selected_codes]


def _registration_price(modules, selected_codes):
    selected = _selected_rows(modules, selected_codes)
    modules_price = sum((Decimal(str(m["monthly_price"] or 0)) for m in selected), Decimal("0"))
    return modules_price, REGISTRATION_BASE_PRICE + modules_price


def _render_registration(*, modules, selected_codes, selected_plan, error=None, form=None):
    modules_price, total = _registration_price(modules, selected_codes)
    return render_template(
        "register_modular.html",
        modules=modules,
        selected_codes=selected_codes,
        selected_plan=selected_plan,
        selected_plan_info=REGISTRATION_PLANS[selected_plan],
        base_price=REGISTRATION_BASE_PRICE,
        modules_price=modules_price,
        monthly_total=total,
        error=error,
        form=form,
    )


def register_modular():
    selected_plan = normalize_registration_plan(
        request.form.get("plan")
        or request.args.get("plan")
        or session.get("selected_plan")
    )
    session["selected_plan"] = selected_plan

    conn = get_db()
    cur = conn.cursor()
    try:
        modules = _registration_modules(cur)
        conn.commit()

        available_codes = {m["code"] for m in modules}
        core_codes = {m["code"] for m in modules if m["is_core"]}

        if request.method == "POST":
            requested_codes = set(request.form.getlist("modules")) & available_codes
            selected_codes = requested_codes | core_codes
        else:
            selected_codes = _default_codes(selected_plan, modules)

        if request.method != "POST":
            return _render_registration(
                modules=modules,
                selected_codes=selected_codes,
                selected_plan=selected_plan,
            )

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        name = request.form.get("name", "").strip()
        director = request.form.get("director", "").strip()
        bin_value = request.form.get("bin", "").strip()
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip()
        iik = request.form.get("iik", "").strip()
        bik = request.form.get("bik", "").strip()
        bank = request.form.get("bank", "").strip()
        kbe = request.form.get("kbe", "").strip()
        knp = request.form.get("knp", "").strip()

        def registration_error(message):
            return _render_registration(
                modules=modules,
                selected_codes=selected_codes,
                selected_plan=selected_plan,
                error=message,
                form=request.form,
            )

        if not username or not password or not name:
            return registration_error("Укажите название компании, логин и пароль.")
        if len(password) < 6:
            return registration_error("Пароль должен содержать минимум 6 символов.")

        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            return registration_error("Такой логин уже используется.")

        modules_price, monthly_total = _registration_price(modules, selected_codes)

        cur.execute("""
            INSERT INTO companies (
                name, director, bin, address, phone,
                iik, bik, bank, kbe, knp, tariff, is_active
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
            RETURNING id
        """, (
            name, director or None, bin_value or None, address or None, phone or None,
            iik or None, bik or None, bank or None, kbe or None, knp or None,
            selected_plan,
        ))
        company_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO users (
                username, password, role, position, company_id,
                full_name, phone, is_super_admin, created_at
            )
            VALUES (%s,%s,'owner','Владелец',%s,%s,%s,FALSE,%s)
            RETURNING id
        """, (
            username, password, company_id, director or username, phone or None, now_kz()
        ))
        owner_id = cur.fetchone()["id"]
        cur.execute("UPDATE companies SET owner_id = %s WHERE id = %s", (owner_id, company_id))

        cur.execute("""
            INSERT INTO company_subscriptions (
                company_id, status, billing_period, base_price,
                employees_price, modules_price, total_price,
                trial_ends_at, period_start, next_payment_at, updated_at
            )
            VALUES (
                %s, 'trial', 'month', %s,
                0, %s, %s,
                NOW() + INTERVAL '14 days', NOW(), NOW() + INTERVAL '14 days', NOW()
            )
            ON CONFLICT (company_id) DO UPDATE SET
                status = 'trial',
                billing_period = 'month',
                base_price = EXCLUDED.base_price,
                employees_price = EXCLUDED.employees_price,
                modules_price = EXCLUDED.modules_price,
                total_price = EXCLUDED.total_price,
                trial_ends_at = EXCLUDED.trial_ends_at,
                period_start = EXCLUDED.period_start,
                next_payment_at = EXCLUDED.next_payment_at,
                updated_at = NOW()
        """, (company_id, REGISTRATION_BASE_PRICE, modules_price, monthly_total))

        for module in modules:
            enabled = bool(module["is_core"] or module["code"] in selected_codes)
            cur.execute("""
                INSERT INTO company_modules (
                    company_id, module_id, enabled, status, price, billing_period,
                    activated_at, expires_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,'month',NOW(),%s,NOW())
                ON CONFLICT (company_id, module_id) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    status = EXCLUDED.status,
                    price = EXCLUDED.price,
                    billing_period = EXCLUDED.billing_period,
                    activated_at = CASE WHEN EXCLUDED.enabled THEN COALESCE(company_modules.activated_at, NOW()) ELSE company_modules.activated_at END,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
            """, (
                company_id,
                module["id"],
                enabled,
                "trial" if enabled else "disabled",
                module["monthly_price"] or 0,
                now_kz() + __import__("datetime").timedelta(days=14) if enabled else None,
            ))

        conn.commit()

        user = {
            "id": owner_id,
            "username": username,
            "role": "owner",
            "company_id": company_id,
            "full_name": director or username,
            "phone": phone or None,
            "percent_rate": 0,
            "is_super_admin": False,
        }

        session.clear()
        session["user_id"] = owner_id
        session["username"] = username
        session["role"] = "owner"
        session["company_id"] = company_id
        session["full_name"] = director or username
        session["phone"] = phone or None
        session["percent_rate"] = 0
        session["is_super_admin"] = False
        session["is_creator"] = False
        session["selected_plan"] = selected_plan
        session["selected_plan_label"] = REGISTRATION_PLANS[selected_plan]["name"]
        session["selected_plan_price"] = float(monthly_total)
        session["employee_modules"] = load_user_module_codes(user)
        session["presence_heartbeat_at"] = now_kz().isoformat()
        session.permanent = True

        return redirect("/onboarding")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def onboarding_modular():
    if not (session.get("user_id") and session.get("company_id")):
        return redirect("/login")

    company_id = session["company_id"]
    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        ensure_onboarding_row(cur, company_id, user_id)
        conn.commit()
        cur.execute("""
            SELECT
                c.id, c.name, c.bin, c.address, c.phone, c.city,
                c.business_type, c.tariff,
                cs.base_price, cs.modules_price, cs.total_price, cs.trial_ends_at,
                op.*
            FROM companies c
            LEFT JOIN company_subscriptions cs ON cs.company_id = c.id
            LEFT JOIN onboarding_progress op ON op.company_id = c.id
            WHERE c.id = %s
        """, (company_id,))
        company = cur.fetchone()
        if company and company.get("completed"):
            return redirect("/analytics")
        if company:
            company = dict(company)
            company["base_price"] = company.get("total_price") or company.get("base_price") or REGISTRATION_BASE_PRICE
        return render_template("onboarding.html", company=company, presets=BUSINESS_PRESETS)
    finally:
        cur.close()
        pool.putconn(conn)


def onboarding_save_modular():
    if not (session.get("user_id") and session.get("company_id")):
        return redirect("/login")

    company_id = session["company_id"]
    user_id = session["user_id"]
    business_type = (request.form.get("business_type") or "other").strip()
    city = (request.form.get("city") or "").strip()
    address = (request.form.get("address") or "").strip()

    sells_products = request.form.get("sells_products") == "1"
    sells_services = request.form.get("sells_services") == "1"
    has_stock = request.form.get("has_stock") == "1"
    has_employees = request.form.get("has_employees") == "1"
    needs_cashbox = request.form.get("needs_cashbox") == "1"
    needs_accounting = request.form.get("needs_accounting") == "1"
    needs_reports = request.form.get("needs_reports") == "1"
    needs_clients = request.form.get("needs_clients") == "1"
    needs_tasks = request.form.get("needs_tasks") == "1"

    try:
        employee_count = max(0, min(int((request.form.get("employee_count") or "0").strip()), 10000))
    except ValueError:
        employee_count = 0

    conn = get_db()
    cur = conn.cursor()
    try:
        ensure_onboarding_row(cur, company_id, user_id)
        cur.execute("""
            SELECT m.code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = %s
              AND cm.enabled = TRUE
              AND m.is_active = TRUE
            ORDER BY m.sort_order, m.id
        """, (company_id,))
        selected_modules = [row["code"] for row in cur.fetchall()]

        cur.execute("""
            UPDATE companies
            SET business_type = %s,
                city = NULLIF(%s, ''),
                address = COALESCE(NULLIF(%s, ''), address)
            WHERE id = %s
        """, (business_type, city, address, company_id))

        cur.execute("""
            UPDATE onboarding_progress
            SET current_step = 6,
                business_type = %s,
                has_products = %s,
                has_employees = %s,
                employee_count = %s,
                needs_cashbox = %s,
                needs_accounting = %s,
                sells_services = %s,
                has_stock = %s,
                needs_reports = %s,
                needs_clients = %s,
                needs_tasks = %s,
                selected_modules = %s,
                updated_at = NOW()
            WHERE company_id = %s
        """, (
            business_type, sells_products, has_employees, employee_count,
            needs_cashbox, needs_accounting, sells_services, has_stock,
            needs_reports, needs_clients, needs_tasks,
            selected_modules, company_id,
        ))
        conn.commit()
        return redirect(url_for("onboarding.onboarding_finish"))
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def onboarding_finish_modular():
    if not (session.get("user_id") and session.get("company_id")):
        return redirect("/login")

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            cur.execute("""
                UPDATE onboarding_progress
                SET completed = TRUE, completed_at = NOW(), current_step = 7, updated_at = NOW()
                WHERE company_id = %s
            """, (company_id,))
            conn.commit()
            return redirect("/analytics")

        cur.execute("""
            SELECT
                c.name, c.business_type, c.city, c.address, c.tariff,
                cs.base_price, cs.modules_price, cs.total_price, cs.trial_ends_at,
                op.*
            FROM companies c
            LEFT JOIN company_subscriptions cs ON cs.company_id = c.id
            LEFT JOIN onboarding_progress op ON op.company_id = c.id
            WHERE c.id = %s
        """, (company_id,))
        setup = cur.fetchone()
        if setup:
            setup = dict(setup)
            setup["base_price"] = setup.get("total_price") or setup.get("base_price") or REGISTRATION_BASE_PRICE

        cur.execute("""
            SELECT m.code, m.name, m.description
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = %s
              AND cm.enabled = TRUE
              AND m.is_active = TRUE
            ORDER BY m.sort_order, m.id
        """, (company_id,))
        enabled_modules = cur.fetchall()

        checklist = []
        if setup.get("has_products") or setup.get("sells_services"):
            checklist.append({
                "title": "Добавьте первые товары или услуги",
                "description": "Каталог уже подключён. Можно начать с 3–5 основных позиций.",
                "url": "/items",
                "button": "Открыть каталог",
            })
        if setup.get("needs_cashbox"):
            checklist.append({
                "title": "Подключите кассу",
                "description": "Настройте ККМ / reKassa / POS и сделайте тестовую продажу.",
                "url": "/settings",
                "button": "Настроить кассу",
            })
        if setup.get("has_employees"):
            checklist.append({
                "title": "Добавьте сотрудников",
                "description": f"Вы указали сотрудников: {setup.get('employee_count') or 0}. Создайте им доступы и роли.",
                "url": "/users",
                "button": "Добавить сотрудников",
            })
        if setup.get("needs_accounting"):
            checklist.append({
                "title": "Проверьте бухгалтерию",
                "description": "Если модуль бухгалтерии выбран, он уже доступен на пробном периоде.",
                "url": "/accounting",
                "button": "Открыть бухгалтерию",
            })
        if any(m["code"] == "sales" for m in enabled_modules):
            checklist.append({
                "title": "Проведите первую продажу",
                "description": "После первой операции Nika начнёт строить реальную аналитику бизнеса.",
                "url": "/sales",
                "button": "Перейти к продаже",
            })

        return render_template(
            "onboarding_finish.html",
            setup=setup,
            enabled_modules=enabled_modules,
            checklist=checklist,
            presets=BUSINESS_PRESETS,
        )
    finally:
        cur.close()
        pool.putconn(conn)
