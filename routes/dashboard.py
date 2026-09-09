from flask import Blueprint, render_template, session, redirect
from models import get_db, pool
from datetime import datetime
from utils.timezone import now_kz
from flask import jsonify

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
def dashboard():
    """Совместимый старый адрес: бизнес-показатели теперь живут только в Аналитике."""
    if not session.get("user_id"):
        return redirect("/login")
    return redirect("/analytics")

@dashboard_bp.route("/api/dashboard")
def api_dashboard():

    if not session.get("user_id"):
        return jsonify({
            "success": False
        }), 401

    conn = get_db()
    cur = conn.cursor()

    company_id = session.get("company_id")

    # Выручка сегодня
    today_str = now_kz().strftime("%Y-%m-%d")

    cur.execute("""
        SELECT SUM(total_amount) as total
        FROM sales
        WHERE DATE(created_at) = %s
        AND company_id = %s
    """, (today_str, company_id))

    today = cur.fetchone()["total"] or 0

    # Клиенты
    cur.execute("""
        SELECT COUNT(*) as total
        FROM clients
        WHERE company_id = %s
    """, (company_id,))

    clients = cur.fetchone()["total"]

    # Товары
    cur.execute("""
        SELECT COUNT(*) as total
        FROM items
        WHERE company_id = %s
    """, (company_id,))

    items = cur.fetchone()["total"]

    # Продажи сегодня
    cur.execute("""
        SELECT COUNT(*) as total
        FROM sales
        WHERE DATE(created_at) = %s
        AND company_id = %s
    """, (today_str, company_id))

    sales_today = cur.fetchone()["total"]

    pool.putconn(conn)

    return jsonify({
        "success": True,
        "today": float(today),
        "clients": clients,
        "items": items,
        "sales_today": sales_today
    })
