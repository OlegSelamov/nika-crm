from flask import Blueprint, render_template, request, redirect, session, url_for
from models import get_db, pool

onboarding_bp = Blueprint("onboarding", __name__)

BUSINESS_PRESETS = {
    "retail": {
        "name": "Магазин / розница",
        "modules": ["sales", "catalog", "warehouse", "clients", "analytics"],
    },
    "services": {
        "name": "Услуги",
        "modules": ["sales", "catalog", "clients", "analytics", "tasks"],
    },
    "cafe": {
        "name": "Кафе / общепит",
        "modules": ["sales", "catalog", "warehouse", "clients", "analytics"],
    },
    "beauty": {
        "name": "Салон / красота",
        "modules": ["sales", "catalog", "clients", "analytics", "tasks"],
    },
    "wholesale": {
        "name": "Оптовая торговля",
        "modules": ["sales", "catalog", "warehouse", "clients", "analytics"],
    },
    "other": {
        "name": "Другой бизнес",
        "modules": ["sales", "catalog", "clients", "analytics"],
    },
}


def login_required():
    return bool(session.get("user_id") and session.get("company_id"))


def ensure_onboarding_row(cur, company_id, owner_user_id):
    cur.execute("""
        INSERT INTO onboarding_progress (
            company_id,
            owner_user_id,
            current_step,
            completed,
            created_at,
            updated_at
        )
        VALUES (%s, %s, 1, FALSE, NOW(), NOW())
        ON CONFLICT (company_id) DO NOTHING
    """, (company_id, owner_user_id))


def set_modules(cur, company_id, module_codes):
    """Включает выбранные модули на trial. Core-модули остаются включёнными всегда."""
    cur.execute("""
        SELECT id, code, monthly_price, is_core
        FROM modules
        WHERE is_active = TRUE
    """)
    modules = cur.fetchall()

    wanted = set(module_codes)
    for module in modules:
        enabled = bool(module["is_core"] or module["code"] in wanted)

        cur.execute("""
            INSERT INTO company_modules (
                company_id,
                module_id,
                enabled,
                status,
                price,
                billing_period,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 'month', NOW())
            ON CONFLICT (company_id, module_id)
            DO UPDATE SET
                enabled = EXCLUDED.enabled,
                status = EXCLUDED.status,
                price = EXCLUDED.price,
                updated_at = NOW()
        """, (
            company_id,
            module["id"],
            enabled,
            "trial" if enabled else "disabled",
            module["monthly_price"] or 0,
        ))


@onboarding_bp.route("/onboarding")
def onboarding():
    if not login_required():
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
                c.id,
                c.name,
                c.bin,
                c.address,
                c.phone,
                c.city,
                c.business_type,
                cs.trial_ends_at,
                op.*
            FROM companies c
            LEFT JOIN company_subscriptions cs ON cs.company_id = c.id
            LEFT JOIN onboarding_progress op ON op.company_id = c.id
            WHERE c.id = %s
        """, (company_id,))
        company = cur.fetchone()

        if company and company.get("completed"):
            return redirect("/dashboard")

        return render_template(
            "onboarding.html",
            company=company,
            presets=BUSINESS_PRESETS,
        )
    finally:
        cur.close()
        pool.putconn(conn)


@onboarding_bp.route("/onboarding/save", methods=["POST"])
def onboarding_save():
    if not login_required():
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
    employee_count_raw = (request.form.get("employee_count") or "0").strip()
    needs_cashbox = request.form.get("needs_cashbox") == "1"
    needs_accounting = request.form.get("needs_accounting") == "1"
    needs_reports = request.form.get("needs_reports") == "1"
    needs_clients = request.form.get("needs_clients") == "1"
    needs_tasks = request.form.get("needs_tasks") == "1"

    try:
        employee_count = max(0, min(int(employee_count_raw), 10000))
    except ValueError:
        employee_count = 0

    selected_modules = set(BUSINESS_PRESETS.get(
        business_type,
        BUSINESS_PRESETS["other"]
    )["modules"])

    # Динамически корректируем набор.
    if sells_products:
        selected_modules.update(["sales", "catalog"])
    if has_stock:
        selected_modules.add("warehouse")
    else:
        selected_modules.discard("warehouse")

    if sells_services:
        selected_modules.update(["sales", "catalog"])

    if needs_clients:
        selected_modules.add("clients")
    else:
        selected_modules.discard("clients")

    if needs_tasks:
        selected_modules.add("tasks")
    else:
        selected_modules.discard("tasks")

    if needs_accounting:
        selected_modules.update(["accounting", "expenses"])
    else:
        selected_modules.discard("accounting")
        selected_modules.discard("expenses")

    if needs_reports:
        selected_modules.add("reports")
    else:
        selected_modules.discard("reports")

    if needs_cashbox:
        selected_modules.add("cto")
    else:
        selected_modules.discard("cto")

    # Аналитика оставляем полезным рекомендованным модулем.
    selected_modules.add("analytics")

    conn = get_db()
    cur = conn.cursor()
    try:
        ensure_onboarding_row(cur, company_id, user_id)

        cur.execute("""
            UPDATE companies
            SET
                business_type = %s,
                city = NULLIF(%s, ''),
                address = COALESCE(NULLIF(%s, ''), address)
            WHERE id = %s
        """, (business_type, city, address, company_id))

        cur.execute("""
            UPDATE onboarding_progress
            SET
                current_step = 6,
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
            business_type,
            sells_products,
            has_employees,
            employee_count,
            needs_cashbox,
            needs_accounting,
            sells_services,
            has_stock,
            needs_reports,
            needs_clients,
            needs_tasks,
            list(sorted(selected_modules)),
            company_id,
        ))

        set_modules(cur, company_id, selected_modules)

        conn.commit()
        return redirect(url_for("onboarding.onboarding_finish"))

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


@onboarding_bp.route("/onboarding/finish", methods=["GET", "POST"])
def onboarding_finish():
    if not login_required():
        return redirect("/login")

    company_id = session["company_id"]

    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            cur.execute("""
                UPDATE onboarding_progress
                SET
                    completed = TRUE,
                    completed_at = NOW(),
                    current_step = 7,
                    updated_at = NOW()
                WHERE company_id = %s
            """, (company_id,))
            conn.commit()
            return redirect("/dashboard")

        cur.execute("""
            SELECT
                c.name,
                c.business_type,
                c.city,
                c.address,
                cs.trial_ends_at,
                op.*
            FROM companies c
            LEFT JOIN company_subscriptions cs ON cs.company_id = c.id
            LEFT JOIN onboarding_progress op ON op.company_id = c.id
            WHERE c.id = %s
        """, (company_id,))
        setup = cur.fetchone()

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

        # Персональный план запуска.
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
                "description": "Настройте ККМ / Rekassa / POS и сделайте тестовую продажу.",
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
                "description": "Nika уже подключила бухгалтерию и расходы на пробный период.",
                "url": "/accounting",
                "button": "Открыть бухгалтерию",
            })

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
