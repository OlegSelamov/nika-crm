from functools import wraps
from flask import g, redirect, request, session, url_for
from models import get_db, pool

PUBLIC_ENDPOINTS = {
    "auth.login", "auth.logout", "auth.register", "auth.api_login",
    "landing", "static", "subscriptions.subscription", "subscriptions.subscription_update"
}


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

    g.company_modules = get_company_module_codes(company_id)
    g.company_subscription = get_company_subscription(company_id)
