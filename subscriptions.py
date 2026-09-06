from functools import wraps
from flask import g, redirect, request, session, url_for
from models import get_db, pool
from utils.timezone import now_kz

PUBLIC_ENDPOINTS = {
    "auth.login", "auth.logout", "auth.register", "auth.api_login",
    "landing", "static", "subscriptions.subscription", "subscriptions.subscription_update"
}



def _ensure_subscription_notifications(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            notification_type VARCHAR(40) DEFAULT 'system',
            title TEXT NOT NULL,
            message TEXT,
            related_id INTEGER,
            link TEXT,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_subscription_unique
        ON notifications(company_id, user_id, notification_type, related_id)
        WHERE notification_type IN (
            'subscription_trial_3d',
            'subscription_trial_1d',
            'subscription_trial_expired',
            'subscription_payment_required'
        )
    """)


def _notify_subscription(cur, company_id, subscription_id, notification_type, title, message):
    _ensure_subscription_notifications(cur)
    cur.execute("""
        SELECT id
        FROM users
        WHERE company_id = %s
          AND (
              id = (SELECT owner_id FROM companies WHERE id = %s)
              OR role = 'owner'
          )
        ORDER BY id
    """, (company_id, company_id))
    user_ids = {row["id"] for row in cur.fetchall()}
    for user_id in user_ids:
        cur.execute("""
            INSERT INTO notifications (
                company_id, user_id, notification_type, title, message,
                related_id, link, is_read, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,'/subscription',FALSE,%s)
            ON CONFLICT DO NOTHING
        """, (
            company_id, user_id, notification_type, title, message,
            subscription_id, now_kz(),
        ))


def sync_subscription_lifecycle(company_id):
    """Synchronize trial status and owner notifications on every authenticated request."""
    if not company_id:
        return None

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT *
            FROM company_subscriptions
            WHERE company_id = %s
            ORDER BY id DESC
            LIMIT 1
            FOR UPDATE
        """, (company_id,))
        subscription = cur.fetchone()
        if not subscription:
            return None

        if subscription["status"] == "pending_payment":
            _notify_subscription(
                cur, company_id, subscription["id"],
                "subscription_payment_required",
                "Требуется оплата подписки",
                "Рабочий доступ к Nika Business приостановлен до подтверждения оплаты. Откройте подписку и завершите оплату.",
            )

        if subscription["status"] == "trial" and subscription.get("trial_ends_at"):
            cur.execute("""
                SELECT
                    CASE
                        WHEN trial_ends_at <= NOW() THEN 'expired'
                        WHEN trial_ends_at <= NOW() + INTERVAL '1 day' THEN '1d'
                        WHEN trial_ends_at <= NOW() + INTERVAL '3 days' THEN '3d'
                        ELSE 'ok'
                    END AS trial_state
                FROM company_subscriptions
                WHERE id = %s
            """, (subscription["id"],))
            trial_state = cur.fetchone()["trial_state"]

            if trial_state == "expired":
                cur.execute("""
                    UPDATE company_subscriptions
                    SET status = 'expired',
                        next_payment_at = COALESCE(next_payment_at, trial_ends_at),
                        updated_at = NOW()
                    WHERE id = %s AND status = 'trial'
                """, (subscription["id"],))
                cur.execute("""
                    UPDATE company_modules
                    SET status = 'expired'
                    WHERE company_id = %s
                      AND status = 'trial'
                """, (company_id,))
                _notify_subscription(
                    cur, company_id, subscription["id"],
                    "subscription_trial_expired",
                    "Пробный период завершён",
                    "Доступ к рабочим разделам Nika Business приостановлен. Выберите подписку, чтобы продолжить работу.",
                )
            elif trial_state == "1d":
                _notify_subscription(
                    cur, company_id, subscription["id"],
                    "subscription_trial_1d",
                    "Пробный период заканчивается",
                    "До окончания пробного периода Nika Business осталось меньше суток. Выберите подписку, чтобы сохранить доступ.",
                )
            elif trial_state == "3d":
                _notify_subscription(
                    cur, company_id, subscription["id"],
                    "subscription_trial_3d",
                    "До конца пробного периода 3 дня",
                    "Пробный период Nika Business скоро завершится. Можно заранее выбрать подписку.",
                )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)

    return get_company_subscription(company_id)


def get_company_subscription(company_id):
    if not company_id:
        return None
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT *
            FROM company_subscriptions
            WHERE company_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (company_id,))
        return cur.fetchone()
    finally:
        cur.close()
        pool.putconn(conn)


def get_company_module_codes(company_id, only_enabled=True):
    if not company_id:
        return set()
    conn = get_db()
    cur = conn.cursor()
    try:
        sql = """
            SELECT m.code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = %s
              AND m.is_active = TRUE
        """
        if only_enabled:
            sql += " AND cm.enabled = TRUE AND cm.status IN ('trial', 'active')"
        cur.execute(sql, (company_id,))
        return {row["code"] for row in cur.fetchall()}
    finally:
        cur.close()
        pool.putconn(conn)


def has_module(company_id, module_code):
    return module_code in get_company_module_codes(company_id)


def module_required(module_code):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if session.get("is_super_admin"):
                return view_func(*args, **kwargs)

            company_id = session.get("company_id")
            if not company_id:
                return redirect(url_for("auth.login"))

            if not has_module(company_id, module_code):
                return redirect(url_for(
                    "subscriptions.subscription",
                    required=module_code,
                    next=request.path,
                ))

            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def load_subscription_context():
    company_id = session.get("company_id")
    if not company_id:
        g.company_modules = set()
        g.company_subscription = None
        return

    if session.get("is_super_admin"):
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("SELECT code FROM modules WHERE is_active = TRUE")
            g.company_modules = {row["code"] for row in cur.fetchall()}
        finally:
            cur.close()
            pool.putconn(conn)
        g.company_subscription = None
        return

    # Trial expiration is enforced lazily on normal user activity, so it
    # works with Gunicorn without a separate scheduler/cron.
    g.company_subscription = sync_subscription_lifecycle(company_id)
    g.company_modules = get_company_module_codes(company_id)
