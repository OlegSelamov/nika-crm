from flask import Blueprint, render_template, session
from models import get_db, pool
from datetime import datetime
from utils.timezone import now_kz
from flask import jsonify

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
def dashboard():
    conn = get_db()
    
    cur = conn.cursor()

    company_id = session.get("company_id")

    # 💰 ОБЩАЯ ВЫРУЧКА
    cur.execute("""
        SELECT SUM(total_amount) as total
        FROM sales
        WHERE company_id = %s
    """, (company_id,))

    total = cur.fetchone()["total"] or 0

    # 📅 СЕГОДНЯ
    today_str = now_kz().strftime("%Y-%m-%d")

    cur.execute("""
        SELECT SUM(total_amount) as total
        FROM sales
        WHERE DATE(created_at) = %s
        AND company_id = %s
    """, (today_str, company_id))

    today = cur.fetchone()["total"] or 0

    # 💳 ОПЛАТЫ
    cur.execute("""
        SELECT 
            SUM(cash_amount) as cash,
            SUM(card_amount) as card,
            SUM(kaspi_amount) as kaspi
        FROM sales
        WHERE company_id = %s
    """, (company_id,))

    payments = cur.fetchone()

    # 🧾 ПОСЛЕДНИЕ ПРОДАЖИ
    cur.execute("""
        SELECT sales.*, clients.full_name
        FROM sales
        LEFT JOIN clients ON sales.client_id = clients.id
        WHERE sales.company_id = %s
        ORDER BY sales.id DESC
        LIMIT 5
    """, (company_id,))

    sales = cur.fetchall()

    # 📈 ГРАФИК
    cur.execute("""
        SELECT DATE(created_at) as date, SUM(total_amount) as total
        FROM sales
        WHERE company_id = %s
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 7
    """, (company_id,))
    
    chart_data = cur.fetchall()

    chart_labels = []
    chart_values = []

    for row in reversed(chart_data):

        chart_labels.append(
            row["date"].strftime("%d.%m")
        )

        chart_values.append(
            row["total"] or 0
        )
        
    # ⚠️ ДОЛГИ
    cur.execute("""
        SELECT clients.full_name, sales.total_amount, sales.paid_amount
        FROM sales
        JOIN clients ON sales.client_id = clients.id
        WHERE sales.company_id = %s
        AND sales.status != 'Оплачено'
        ORDER BY sales.id DESC
        LIMIT 5
    """, (company_id,))
    
    debts = cur.fetchall()
    
    # 🔔 УВЕДОМЛЕНИЯ
    notifications = []

    for d in debts:
        notifications.append(f"Долг: {d['full_name']}")

    cur.execute("""
        SELECT id FROM sales
        WHERE company_id = %s
        ORDER BY id DESC
        LIMIT 3
    """, (company_id,))
    
    recent = cur.fetchall()

    for r in recent:
        notifications.append(f"Новая продажа #{r['id']}")
      
    
    cur.execute("""

    SELECT
        items.name,

        COALESCE(
            SUM(
                CASE
                    WHEN stock_movements.movement_type='income'
                    THEN stock_movements.quantity

                    WHEN stock_movements.movement_type='sale'
                    THEN -stock_movements.quantity

                    WHEN stock_movements.movement_type='writeoff'
                    THEN -stock_movements.quantity
                END
            ),
            0
        ) as stock

    FROM items

    LEFT JOIN stock_movements
    ON items.id = stock_movements.item_id

    WHERE items.company_id = %s

    GROUP BY items.id

    HAVING
    COALESCE(
        SUM(
            CASE
                WHEN stock_movements.movement_type='income'
                THEN stock_movements.quantity

                WHEN stock_movements.movement_type='sale'
                THEN -stock_movements.quantity

                WHEN stock_movements.movement_type='writeoff'
                THEN -stock_movements.quantity
            END
        ),
        0
    ) <= 5

    ORDER BY stock ASC

    """, (
        session.get("company_id"),
    ))
    
    low_stock = cur.fetchall() 

    pool.putconn(conn)   
    
    return render_template(
        "dashboard.html",
        total=total,
        today=today,
        payments=payments,
        sales=sales,
        chart_labels=chart_labels,
        chart_values=chart_values,
        debts=debts,
        low_stock=low_stock,
        notifications=notifications
    )
    
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