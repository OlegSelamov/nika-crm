from flask import redirect, request, session, url_for

from models import get_db, pool
from routes.subscriptions import (
    BASE_MONTHLY_PRICE,
    calculate_total,
    employee_price,
    subscriptions_bp,
)


def _owner_allowed():
    return bool(
        session.get("role") == "owner"
        or session.get("is_creator")
        or session.get("is_super_admin")
    )


@subscriptions_bp.route("/subscription/selection", methods=["POST"])
def save_subscription_selection():
    """Save module selection without forcing payment while the trial is active."""
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))
    if not _owner_allowed():
        return "Только владелец компании может менять подписку", 403

    company_id = session.get("company_id")
    if not company_id:
        return "Компания не выбрана", 400

    selected_codes = set(request.form.getlist("modules"))
    billing_period = request.form.get("billing_period", "month")
    if billing_period not in {"month", "year"}:
        billing_period = "month"

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT *
            FROM company_subscriptions
            WHERE company_id = %s
            FOR UPDATE
        """, (company_id,))
        subscription = cur.fetchone()
        if not subscription:
            return "Подписка компании не найдена", 404

        cur.execute("""
            SELECT *
            FROM modules
            WHERE is_active = TRUE
              AND code <> 'cto'
            ORDER BY id
        """)
        all_modules = cur.fetchall()
        selected_modules = [
            module for module in all_modules
            if module["is_core"] or module["code"] in selected_codes
        ]

        cur.execute("SELECT COUNT(*) AS count FROM users WHERE company_id = %s", (company_id,))
        employee_count = cur.fetchone()["count"] or 0
        employees_total = employee_price(employee_count)
        monthly_total, payable_total = calculate_total(selected_modules, employee_count, billing_period)
        modules_total = monthly_total - BASE_MONTHLY_PRICE - employees_total

        is_trial = subscription["status"] == "trial"
        next_status = "trial" if is_trial else "pending_payment"

        if is_trial:
            # Preserve trial_ends_at: adding a module never restarts or extends trial.
            cur.execute("""
                UPDATE company_subscriptions
                SET billing_period = %s,
                    base_price = %s,
                    employees_price = %s,
                    modules_price = %s,
                    total_price = %s,
                    updated_at = NOW()
                WHERE company_id = %s
            """, (
                billing_period,
                BASE_MONTHLY_PRICE,
                employees_total,
                modules_total,
                payable_total,
                company_id,
            ))
        else:
            cur.execute("""
                UPDATE company_subscriptions
                SET status = 'pending_payment',
                    billing_period = %s,
                    base_price = %s,
                    employees_price = %s,
                    modules_price = %s,
                    total_price = %s,
                    next_payment_at = NOW(),
                    updated_at = NOW()
                WHERE company_id = %s
            """, (
                billing_period,
                BASE_MONTHLY_PRICE,
                employees_total,
                modules_total,
                payable_total,
                company_id,
            ))

        selected_ids = {module["id"] for module in selected_modules}
        trial_ends_at = subscription.get("trial_ends_at")

        for module in all_modules:
            enabled = module["id"] in selected_ids
            module_status = next_status if enabled else "disabled"
            expires_at = trial_ends_at if (is_trial and enabled) else None
            cur.execute("""
                INSERT INTO company_modules (
                    company_id, module_id, enabled, status, price,
                    billing_period, activated_at, expires_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s,NOW())
                ON CONFLICT (company_id, module_id)
                DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    status = EXCLUDED.status,
                    price = EXCLUDED.price,
                    billing_period = EXCLUDED.billing_period,
                    activated_at = CASE
                        WHEN EXCLUDED.enabled THEN COALESCE(company_modules.activated_at, NOW())
                        ELSE company_modules.activated_at
                    END,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
            """, (
                company_id,
                module["id"],
                enabled,
                module_status,
                module["monthly_price"] or 0,
                billing_period,
                expires_at,
            ))

        conn.commit()

        if is_trial:
            return redirect("/subscription?saved=1")
        return redirect(url_for("subscriptions.epay_start"))

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)
