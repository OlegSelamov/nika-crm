from flask import Blueprint, render_template, session
from models import get_db
from datetime import datetime
import sqlite3

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
def dashboard():
    conn = get_db()
    conn.row_factory = sqlite3.Row

    company_id = session.get("company_id")

    # 💰 ОБЩАЯ ВЫРУЧКА
    total = conn.execute("""
        SELECT SUM(total_amount) as total
        FROM sales
        WHERE company_id = ?
    """, (company_id,)).fetchone()["total"] or 0

    # 📅 СЕГОДНЯ
    today_str = datetime.now().strftime("%Y-%m-%d")

    today = conn.execute("""
        SELECT SUM(total_amount) as total
        FROM sales
        WHERE DATE(created_at) = ?
        AND company_id = ?
    """, (today_str, company_id)).fetchone()["total"] or 0

    # 💳 ОПЛАТЫ
    payments = conn.execute("""
        SELECT 
            SUM(cash_amount) as cash,
            SUM(card_amount) as card,
            SUM(kaspi_amount) as kaspi
        FROM sales
        WHERE company_id = ?
    """, (company_id,)).fetchone()

    # 🧾 ПОСЛЕДНИЕ ПРОДАЖИ
    sales = conn.execute("""
        SELECT sales.*, clients.full_name
        FROM sales
        LEFT JOIN clients ON sales.client_id = clients.id
        WHERE sales.company_id = ?
        ORDER BY sales.id DESC
        LIMIT 5
    """, (company_id,)).fetchall()

    # 📈 ГРАФИК
    chart_data = conn.execute("""
        SELECT DATE(created_at) as date, SUM(total_amount) as total
        FROM sales
        WHERE company_id = ?
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 7
    """, (company_id,)).fetchall()

    chart_labels = []
    chart_values = []

    for row in reversed(chart_data):
        chart_labels.append(row["date"])
        chart_values.append(row["total"] or 0)
        
    # ⚠️ ДОЛГИ
    debts = conn.execute("""
        SELECT clients.full_name, sales.total_amount, sales.paid_amount
        FROM sales
        JOIN clients ON sales.client_id = clients.id
        WHERE sales.company_id = ?
        AND sales.status != 'Оплачено'
        ORDER BY sales.id DESC
        LIMIT 5
    """, (company_id,)).fetchall()
    
    # 🔔 УВЕДОМЛЕНИЯ
    notifications = []

    for d in debts:
        notifications.append(f"Долг: {d['full_name']}")

    recent = conn.execute("""
        SELECT id FROM sales
        WHERE company_id = ?
        ORDER BY id DESC
        LIMIT 3
    """, (company_id,)).fetchall()

    for r in recent:
        notifications.append(f"Новая продажа #{r['id']}")
        
    conn.close()
        
    return render_template(
        "dashboard.html",
        total=total,
        today=today,
        payments=payments,
        sales=sales,
        chart_labels=chart_labels,
        chart_values=chart_values,
        debts=debts,
        notifications=notifications
    )