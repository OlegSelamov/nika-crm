from functools import wraps
from datetime import datetime
from flask import (
    Blueprint,
    render_template,
    session,
    redirect,
    url_for,
    request,
    flash,
)
from models import get_db, pool

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def super_admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))

        if not session.get("is_super_admin"):
            return "Доступ запрещён", 403

        return view_func(*args, **kwargs)

    return wrapped


def get_admin_company(company_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                c.*,
                u.id AS owner_user_id,
                u.full_name AS owner_name,
                u.username AS owner_username,
                u.phone AS owner_phone,
                u.last_login_at AS owner_last_login_at,
                u.last_seen_at AS owner_last_seen_at,
                u.created_at AS owner_created_at,
                cs.id AS subscription_id,
                cs.status AS subscription_status,
                cs.billing_period,
                cs.base_price,
                cs.employees_price,
                cs.branches_price,
                cs.modules_price,
                cs.discount,
                cs.total_price,
                cs.trial_ends_at,
                cs.period_start,
                cs.period_end,
                cs.next_payment_at,
                cs.auto_renew,
                cs.created_at AS subscription_created_at,
                cs.updated_at AS subscription_updated_at
            FROM companies c
            LEFT JOIN users u ON u.id = c.owner_id
            LEFT JOIN company_subscriptions cs ON cs.company_id = c.id
            WHERE c.id = %s
            LIMIT 1
        """, (company_id,))
        return cur.fetchone()
    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/")
@super_admin_required
def dashboard():
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("SELECT COUNT(*) AS count FROM companies")
        companies_count = cur.fetchone()["count"] or 0

        cur.execute("""
            SELECT status, COUNT(*) AS count
            FROM company_subscriptions
            GROUP BY status
        """)
        subscription_rows = cur.fetchall()
        subscription_counts = {
            row["status"]: row["count"]
            for row in subscription_rows
        }

        trial_count = subscription_counts.get("trial", 0)
        active_count = subscription_counts.get("active", 0)
        pending_payment_count = subscription_counts.get("pending_payment", 0)
        expired_count = subscription_counts.get("expired", 0)
        suspended_count = subscription_counts.get("suspended", 0)
        cancelled_count = subscription_counts.get("cancelled", 0)

        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM subscription_payments
            WHERE status = 'paid'
              AND paid_at::date = CURRENT_DATE
        """)
        revenue_today = cur.fetchone()["total"] or 0

        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM subscription_payments
            WHERE status = 'paid'
              AND DATE_TRUNC('month', paid_at) = DATE_TRUNC('month', CURRENT_DATE)
        """)
        revenue_month = cur.fetchone()["total"] or 0

        cur.execute("""
            SELECT COUNT(DISTINCT c.id) AS count
            FROM companies c
            LEFT JOIN users u ON u.id = c.owner_id
            WHERE u.created_at::date = CURRENT_DATE
        """)
        new_today = cur.fetchone()["count"] or 0

        cur.execute("""
            SELECT COUNT(DISTINCT c.id) AS count
            FROM companies c
            LEFT JOIN users u ON u.id = c.owner_id
            WHERE u.created_at >= NOW() - INTERVAL '7 days'
        """)
        new_7_days = cur.fetchone()["count"] or 0

        cur.execute("""
            SELECT
                c.id,
                c.name,
                c.bin,
                c.phone,
                c.address,
                c.is_active,
                c.tariff,
                c.paid_until,
                u.full_name AS owner_name,
                u.username AS owner_username,
                u.last_seen_at,
                u.created_at AS registered_at,
                cs.status AS subscription_status,
                cs.billing_period,
                cs.total_price,
                cs.trial_ends_at,
                cs.period_end,
                cs.next_payment_at
            FROM companies c
            LEFT JOIN users u ON u.id = c.owner_id
            LEFT JOIN company_subscriptions cs ON cs.company_id = c.id
            ORDER BY COALESCE(u.created_at, cs.created_at, NOW()) DESC, c.id DESC
            LIMIT 20
        """)
        recent_companies = cur.fetchall()

        return render_template(
            "admin/dashboard.html",
            companies_count=companies_count,
            trial_count=trial_count,
            active_count=active_count,
            pending_payment_count=pending_payment_count,
            expired_count=expired_count,
            suspended_count=suspended_count,
            cancelled_count=cancelled_count,
            revenue_today=revenue_today,
            revenue_month=revenue_month,
            new_today=new_today,
            new_7_days=new_7_days,
            recent_companies=recent_companies,
        )

    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/companies")
@super_admin_required
def companies():
    search = (request.args.get("q") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    try:
        params = []
        where_sql = ""

        if search:
            where_sql = """
                WHERE
                    COALESCE(c.name, '') ILIKE %s
                    OR COALESCE(c.bin, '') ILIKE %s
                    OR COALESCE(c.phone, '') ILIKE %s
                    OR COALESCE(u.full_name, '') ILIKE %s
                    OR COALESCE(u.username, '') ILIKE %s
            """
            value = f"%{search}%"
            params = [value, value, value, value, value]

        cur.execute(f"""
            SELECT
                c.id,
                c.name,
                c.bin,
                c.phone,
                c.address,
                c.is_active,
                c.tariff,
                c.paid_until,
                u.full_name AS owner_name,
                u.username AS owner_username,
                u.last_seen_at,
                u.created_at AS registered_at,
                cs.status AS subscription_status,
                cs.billing_period,
                cs.total_price,
                cs.trial_ends_at,
                cs.period_end,
                cs.next_payment_at
            FROM companies c
            LEFT JOIN users u ON u.id = c.owner_id
            LEFT JOIN company_subscriptions cs ON cs.company_id = c.id
            {where_sql}
            ORDER BY c.id DESC
            LIMIT 200
        """, params)

        companies_rows = cur.fetchall()

        return render_template(
            "admin/companies.html",
            companies=companies_rows,
            search=search,
        )

    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/companies/<int:company_id>")
@super_admin_required
def company_detail(company_id):
    company = get_admin_company(company_id)
    if not company:
        return "Компания не найдена", 404

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                id,
                full_name,
                username,
                role,
                phone,
                is_creator,
                last_login_at,
                last_seen_at,
                created_at
            FROM users
            WHERE company_id = %s
            ORDER BY is_creator DESC, id
        """, (company_id,))
        employees = cur.fetchall()

        cur.execute("""
            SELECT
                m.id,
                m.code,
                m.name,
                m.category,
                m.is_core,
                m.monthly_price,
                COALESCE(cm.enabled, FALSE) AS enabled,
                cm.status,
                cm.price,
                cm.billing_period,
                cm.activated_at,
                cm.expires_at
            FROM modules m
            LEFT JOIN company_modules cm
              ON cm.module_id = m.id
             AND cm.company_id = %s
            WHERE m.is_active = TRUE
            ORDER BY m.sort_order, m.id
        """, (company_id,))
        modules = cur.fetchall()

        cur.execute("""
            SELECT
                id,
                amount,
                currency,
                provider,
                payment_method,
                provider_payment_id,
                status,
                description,
                paid_at,
                created_at
            FROM subscription_payments
            WHERE company_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        """, (company_id,))
        payments = cur.fetchall()

        cur.execute("""
            SELECT
                id,
                user_id,
                action,
                old_value,
                new_value,
                created_at
            FROM subscription_changes
            WHERE company_id = %s
            ORDER BY created_at DESC
            LIMIT 30
        """, (company_id,))
        changes = cur.fetchall()

        cur.execute("""
            SELECT
                COUNT(*) AS sales_count,
                COALESCE(SUM(total_amount), 0) AS sales_total,
                MAX(created_at) AS last_sale_at
            FROM sales
            WHERE company_id = %s
        """, (company_id,))
        sales_stats = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS items_count
            FROM items
            WHERE company_id = %s
        """, (company_id,))
        items_count = cur.fetchone()["items_count"] or 0

        cur.execute("""
            SELECT COUNT(*) AS clients_count
            FROM clients
            WHERE company_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
        """, (company_id,))
        clients_count = cur.fetchone()["clients_count"] or 0

        return render_template(
            "admin/company_detail.html",
            company=company,
            employees=employees,
            modules=modules,
            payments=payments,
            changes=changes,
            sales_stats=sales_stats,
            items_count=items_count,
            clients_count=clients_count,
        )

    finally:
        cur.close()
        pool.putconn(conn)


def record_subscription_change(cur, company_id, action, old_value, new_value):
    cur.execute("""
        INSERT INTO subscription_changes (
            company_id,
            user_id,
            action,
            old_value,
            new_value,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW())
    """, (
        company_id,
        session.get("user_id"),
        action,
        old_value,
        new_value,
    ))


@admin_bp.route("/companies/<int:company_id>/trial/extend", methods=["POST"])
@super_admin_required
def extend_trial(company_id):
    days = request.form.get("days", "7")
    try:
        days = max(1, min(int(days), 90))
    except ValueError:
        days = 7

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT status, trial_ends_at
            FROM company_subscriptions
            WHERE company_id = %s
            FOR UPDATE
        """, (company_id,))
        old = cur.fetchone()

        if not old:
            cur.execute("""
                INSERT INTO company_subscriptions (
                    company_id,
                    status,
                    billing_period,
                    base_price,
                    trial_ends_at,
                    period_start,
                    next_payment_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s,
                    'trial',
                    'month',
                    2990,
                    NOW() + (%s || ' days')::interval,
                    NOW(),
                    NOW() + (%s || ' days')::interval,
                    NOW(),
                    NOW()
                )
            """, (company_id, days, days))
            old_value = {}
        else:
            old_value = {
                "status": old["status"],
                "trial_ends_at": old["trial_ends_at"].isoformat() if old["trial_ends_at"] else None,
            }

            cur.execute("""
                UPDATE company_subscriptions
                SET
                    status = 'trial',
                    trial_ends_at = GREATEST(
                        COALESCE(trial_ends_at, NOW()),
                        NOW()
                    ) + (%s || ' days')::interval,
                    next_payment_at = GREATEST(
                        COALESCE(trial_ends_at, NOW()),
                        NOW()
                    ) + (%s || ' days')::interval,
                    updated_at = NOW()
                WHERE company_id = %s
            """, (days, days, company_id))

        cur.execute("""
            UPDATE company_modules
            SET
                enabled = TRUE,
                status = CASE
                    WHEN enabled = TRUE THEN 'trial'
                    ELSE status
                END,
                updated_at = NOW()
            WHERE company_id = %s
        """, (company_id,))

        cur.execute("""
            SELECT status, trial_ends_at
            FROM company_subscriptions
            WHERE company_id = %s
        """, (company_id,))
        new = cur.fetchone()

        record_subscription_change(
            cur,
            company_id,
            "admin_extend_trial",
            old_value,
            {
                "status": new["status"],
                "trial_ends_at": new["trial_ends_at"].isoformat() if new["trial_ends_at"] else None,
                "days_added": days,
            },
        )

        conn.commit()
        flash(f"Trial продлён на {days} дн.", "success")
        return redirect(url_for("admin.company_detail", company_id=company_id))

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/companies/<int:company_id>/subscription/activate", methods=["POST"])
@super_admin_required
def activate_subscription(company_id):
    months = request.form.get("months", "1")
    try:
        months = max(1, min(int(months), 24))
    except ValueError:
        months = 1

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT status, period_end, next_payment_at
            FROM company_subscriptions
            WHERE company_id = %s
            FOR UPDATE
        """, (company_id,))
        old = cur.fetchone()

        old_value = {}
        if old:
            old_value = {
                "status": old["status"],
                "period_end": old["period_end"].isoformat() if old["period_end"] else None,
                "next_payment_at": old["next_payment_at"].isoformat() if old["next_payment_at"] else None,
            }

        cur.execute("""
            INSERT INTO company_subscriptions (
                company_id,
                status,
                billing_period,
                base_price,
                period_start,
                period_end,
                next_payment_at,
                auto_renew,
                created_at,
                updated_at
            )
            VALUES (
                %s,
                'active',
                'month',
                2990,
                NOW(),
                NOW() + (%s || ' months')::interval,
                NOW() + (%s || ' months')::interval,
                FALSE,
                NOW(),
                NOW()
            )
            ON CONFLICT (company_id)
            DO UPDATE SET
                status = 'active',
                period_start = NOW(),
                period_end = NOW() + (%s || ' months')::interval,
                next_payment_at = NOW() + (%s || ' months')::interval,
                updated_at = NOW()
        """, (company_id, months, months, months, months))

        cur.execute("""
            UPDATE company_modules
            SET
                status = CASE WHEN enabled = TRUE THEN 'active' ELSE status END,
                expires_at = CASE
                    WHEN enabled = TRUE THEN NOW() + (%s || ' months')::interval
                    ELSE expires_at
                END,
                updated_at = NOW()
            WHERE company_id = %s
        """, (months, company_id))

        cur.execute("""
            SELECT status, period_end, next_payment_at
            FROM company_subscriptions
            WHERE company_id = %s
        """, (company_id,))
        new = cur.fetchone()

        record_subscription_change(
            cur,
            company_id,
            "admin_activate_subscription",
            old_value,
            {
                "status": new["status"],
                "period_end": new["period_end"].isoformat() if new["period_end"] else None,
                "next_payment_at": new["next_payment_at"].isoformat() if new["next_payment_at"] else None,
                "months": months,
            },
        )

        conn.commit()
        flash(f"Подписка активирована на {months} мес.", "success")
        return redirect(url_for("admin.company_detail", company_id=company_id))

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/companies/<int:company_id>/subscription/suspend", methods=["POST"])
@super_admin_required
def suspend_subscription(company_id):
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT status
            FROM company_subscriptions
            WHERE company_id = %s
            FOR UPDATE
        """, (company_id,))
        old = cur.fetchone()

        if not old:
            flash("У компании нет подписки.", "error")
            return redirect(url_for("admin.company_detail", company_id=company_id))

        cur.execute("""
            UPDATE company_subscriptions
            SET status = 'suspended', updated_at = NOW()
            WHERE company_id = %s
        """, (company_id,))

        cur.execute("""
            UPDATE company_modules
            SET
                status = CASE WHEN enabled = TRUE THEN 'suspended' ELSE status END,
                updated_at = NOW()
            WHERE company_id = %s
        """, (company_id,))

        record_subscription_change(
            cur,
            company_id,
            "admin_suspend_subscription",
            {"status": old["status"]},
            {"status": "suspended"},
        )

        conn.commit()
        flash("Подписка приостановлена.", "success")
        return redirect(url_for("admin.company_detail", company_id=company_id))

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/companies/<int:company_id>/enter", methods=["POST"])
@super_admin_required
def enter_company(company_id):
    company = get_admin_company(company_id)
    if not company:
        return "Компания не найдена", 404

    # Сохраняем исходный контекст супер-админа один раз.
    if "admin_original_company_id" not in session:
        session["admin_original_company_id"] = session.get("company_id")
        session["admin_original_role"] = session.get("role")
        session["admin_original_is_creator"] = session.get("is_creator")

    session["company_id"] = company_id
    session["admin_viewing_company_id"] = company_id

    # is_super_admin остаётся True, поэтому доступ к системе не ломается.
    flash(f"Открыта компания: {company['name'] or 'Без названия'}", "success")
    return redirect("/dashboard")


@admin_bp.route("/exit-company", methods=["POST"])
@super_admin_required
def exit_company():
    if "admin_original_company_id" in session:
        session["company_id"] = session.pop("admin_original_company_id", None)
        session["role"] = session.pop("admin_original_role", session.get("role"))
        session["is_creator"] = session.pop(
            "admin_original_is_creator",
            session.get("is_creator"),
        )

    session.pop("admin_viewing_company_id", None)

    flash("Вы вернулись в Nika Admin.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/subscriptions")
@super_admin_required
def subscriptions_overview():
    status_filter = (request.args.get("status") or "").strip()
    q = (request.args.get("q") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE status = 'trial') AS trial_count,
                COUNT(*) FILTER (WHERE status = 'pending_payment') AS pending_count,
                COUNT(*) FILTER (WHERE status = 'expired') AS expired_count,
                COUNT(*) FILTER (WHERE status = 'suspended') AS suspended_count,
                COALESCE(SUM(
                    CASE
                        WHEN status = 'active' AND billing_period = 'month'
                            THEN total_price
                        WHEN status = 'active' AND billing_period = 'year'
                            THEN total_price / 12
                        ELSE 0
                    END
                ), 0) AS estimated_mrr
            FROM company_subscriptions
        """)
        stats = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM company_subscriptions
            WHERE status = 'trial'
              AND trial_ends_at IS NOT NULL
              AND trial_ends_at >= NOW()
              AND trial_ends_at <= NOW() + INTERVAL '3 days'
        """)
        trial_ending_3d = cur.fetchone()["count"] or 0

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM company_subscriptions
            WHERE status = 'active'
              AND next_payment_at IS NOT NULL
              AND next_payment_at < NOW()
        """)
        overdue_active = cur.fetchone()["count"] or 0

        where = []
        params = []

        if status_filter:
            where.append("cs.status = %s")
            params.append(status_filter)

        if q:
            where.append("""
                (
                    COALESCE(c.name, '') ILIKE %s
                    OR COALESCE(c.bin, '') ILIKE %s
                    OR COALESCE(c.phone, '') ILIKE %s
                )
            """)
            value = f"%{q}%"
            params.extend([value, value, value])

        where_sql = ""
        if where:
            where_sql = "WHERE " + " AND ".join(where)

        cur.execute(f"""
            SELECT
                cs.id,
                cs.company_id,
                cs.status,
                cs.billing_period,
                cs.base_price,
                cs.employees_price,
                cs.modules_price,
                cs.discount,
                cs.total_price,
                cs.trial_ends_at,
                cs.period_end,
                cs.next_payment_at,
                cs.auto_renew,
                cs.created_at,
                cs.updated_at,
                c.name AS company_name,
                c.bin,
                c.phone,
                u.full_name AS owner_name,
                u.username AS owner_username,
                u.last_seen_at
            FROM company_subscriptions cs
            JOIN companies c ON c.id = cs.company_id
            LEFT JOIN users u ON u.id = c.owner_id
            {where_sql}
            ORDER BY
                CASE
                    WHEN cs.status = 'pending_payment' THEN 1
                    WHEN cs.status = 'trial' THEN 2
                    WHEN cs.status = 'active' THEN 3
                    WHEN cs.status = 'expired' THEN 4
                    WHEN cs.status = 'suspended' THEN 5
                    ELSE 6
                END,
                COALESCE(cs.next_payment_at, cs.trial_ends_at, cs.updated_at) ASC
            LIMIT 500
        """, params)

        rows = cur.fetchall()

        return render_template(
            "admin/subscriptions.html",
            subscriptions=rows,
            stats=stats,
            trial_ending_3d=trial_ending_3d,
            overdue_active=overdue_active,
            status_filter=status_filter,
            q=q,
        )
    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/payments")
@super_admin_required
def payments_overview():
    status_filter = (request.args.get("status") or "").strip()
    provider_filter = (request.args.get("provider") or "").strip()
    q = (request.args.get("q") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                COALESCE(SUM(amount) FILTER (WHERE status = 'paid'), 0) AS paid_all,
                COALESCE(SUM(amount) FILTER (
                    WHERE status = 'paid'
                      AND paid_at::date = CURRENT_DATE
                ), 0) AS paid_today,
                COALESCE(SUM(amount) FILTER (
                    WHERE status = 'paid'
                      AND DATE_TRUNC('month', paid_at) = DATE_TRUNC('month', CURRENT_DATE)
                ), 0) AS paid_month,
                COUNT(*) FILTER (WHERE status = 'created') AS created_count,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_count
            FROM subscription_payments
        """)
        stats = cur.fetchone()

        where = []
        params = []

        if status_filter:
            where.append("sp.status = %s")
            params.append(status_filter)

        if provider_filter:
            where.append("COALESCE(sp.provider, '') = %s")
            params.append(provider_filter)

        if q:
            where.append("""
                (
                    COALESCE(c.name, '') ILIKE %s
                    OR COALESCE(c.bin, '') ILIKE %s
                    OR COALESCE(sp.provider_payment_id, '') ILIKE %s
                    OR COALESCE(sp.description, '') ILIKE %s
                )
            """)
            value = f"%{q}%"
            params.extend([value, value, value, value])

        where_sql = ""
        if where:
            where_sql = "WHERE " + " AND ".join(where)

        cur.execute(f"""
            SELECT
                sp.id,
                sp.company_id,
                sp.subscription_id,
                sp.amount,
                sp.currency,
                sp.provider,
                sp.payment_method,
                sp.provider_payment_id,
                sp.status,
                sp.description,
                sp.paid_at,
                sp.created_at,
                c.name AS company_name,
                c.bin
            FROM subscription_payments sp
            JOIN companies c ON c.id = sp.company_id
            {where_sql}
            ORDER BY sp.created_at DESC
            LIMIT 500
        """, params)

        payments = cur.fetchall()

        cur.execute("""
            SELECT DISTINCT provider
            FROM subscription_payments
            WHERE provider IS NOT NULL
              AND provider <> ''
            ORDER BY provider
        """)
        providers = [row["provider"] for row in cur.fetchall()]

        return render_template(
            "admin/payments.html",
            payments=payments,
            stats=stats,
            providers=providers,
            status_filter=status_filter,
            provider_filter=provider_filter,
            q=q,
        )
    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/payments/<int:payment_id>/mark-paid", methods=["POST"])
@super_admin_required
def mark_payment_paid(payment_id):
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT *
            FROM subscription_payments
            WHERE id = %s
            FOR UPDATE
        """, (payment_id,))
        payment = cur.fetchone()

        if not payment:
            return "Платёж не найден", 404

        if payment["status"] == "paid":
            flash("Платёж уже отмечен как оплаченный.", "success")
            return redirect(url_for("admin.payments_overview"))

        cur.execute("""
            UPDATE subscription_payments
            SET
                status = 'paid',
                paid_at = COALESCE(paid_at, NOW())
            WHERE id = %s
        """, (payment_id,))

        # Активируем подписку только если это ещё не было сделано.
        cur.execute("""
            UPDATE company_subscriptions
            SET
                status = 'active',
                period_start = COALESCE(period_start, NOW()),
                period_end = CASE
                    WHEN billing_period = 'year'
                        THEN GREATEST(COALESCE(period_end, NOW()), NOW()) + INTERVAL '1 year'
                    ELSE GREATEST(COALESCE(period_end, NOW()), NOW()) + INTERVAL '1 month'
                END,
                next_payment_at = CASE
                    WHEN billing_period = 'year'
                        THEN GREATEST(COALESCE(period_end, NOW()), NOW()) + INTERVAL '1 year'
                    ELSE GREATEST(COALESCE(period_end, NOW()), NOW()) + INTERVAL '1 month'
                END,
                updated_at = NOW()
            WHERE company_id = %s
        """, (payment["company_id"],))

        cur.execute("""
            UPDATE company_modules
            SET
                status = CASE WHEN enabled = TRUE THEN 'active' ELSE status END,
                updated_at = NOW()
            WHERE company_id = %s
        """, (payment["company_id"],))

        record_subscription_change(
            cur,
            payment["company_id"],
            "admin_mark_payment_paid",
            {"payment_id": payment_id, "status": payment["status"]},
            {"payment_id": payment_id, "status": "paid"},
        )

        conn.commit()
        flash("Платёж отмечен как оплаченный, подписка активирована.", "success")
        return redirect(url_for("admin.company_detail", company_id=payment["company_id"]))

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


@admin_bp.route("/billing/webhook/kaspi", methods=["POST"])
def kaspi_webhook_placeholder():
    # Заготовка под будущую официальную интеграцию.
    # До получения технической документации Kaspi ничего не активируем автоматически.
    #
    # В будущем здесь будет:
    # 1) проверка подписи/секрета провайдера;
    # 2) поиск provider_payment_id;
    # 3) защита от повторной обработки webhook;
    # 4) status='paid';
    # 5) активация company_subscriptions;
    # 6) создание чека/документов;
    # 7) запись subscription_changes.
    return {"ok": False, "status": "not_configured"}, 501
