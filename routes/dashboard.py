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
        SELECT COALESCE(SUM(total_amount) FILTER (
                   WHERE status IN ('Оплачено', 'Возврат')), 0)
             - COALESCE(SUM(total_amount) FILTER (
                   WHERE status = 'Возврат' OR COALESCE(is_refunded, FALSE) = TRUE), 0) AS total
        FROM sales WHERE company_id = %s
    """, (company_id,))

    total = cur.fetchone()["total"] or 0

    # 📅 СЕГОДНЯ
    today_str = now_kz().strftime("%Y-%m-%d")

    cur.execute("""
        SELECT COALESCE(SUM(total_amount) FILTER (
                   WHERE status IN ('Оплачено', 'Возврат') AND DATE(created_at) = %s), 0)
             - COALESCE(SUM(total_amount) FILTER (
                   WHERE (status = 'Возврат' OR COALESCE(is_refunded, FALSE) = TRUE)
                     AND DATE(COALESCE(refunded_at, created_at)) = %s), 0) AS total
        FROM sales WHERE company_id = %s
    """, (today_str, today_str, company_id))

    today = cur.fetchone()["total"] or 0
    
    cur.execute("""
        SELECT COUNT(*) AS total
        FROM sales
        WHERE company_id = %s
        AND DATE(created_at) = %s
        AND status IN ('Оплачено', 'Возврат')
    """, (
        company_id,
        today_str
    ))

    sales_today = cur.fetchone()["total"] or 0
    
    cur.execute("""
        SELECT
            COALESCE(AVG(total_amount),0) AS avg_check
        FROM sales
        WHERE company_id=%s
        AND DATE(created_at)=%s
        AND status IN ('Оплачено', 'Возврат')
    """,(
        company_id,
        today_str
    ))

    average_check = cur.fetchone()["avg_check"] or 0
    
    cur.execute("""
    SELECT
    COALESCE(SUM(sale_items.profit),0) AS profit
    FROM sale_items

    JOIN sales
    ON sales.id=sale_items.sale_id

    WHERE sales.company_id=%s
    AND DATE(sales.created_at)=%s
    AND sales.status IN ('Оплачено', 'Возврат')
    """,(
    company_id,
    today_str
    ))

    today_profit = cur.fetchone()["profit"] or 0
    
    cur.execute("""
    SELECT COUNT(*) AS total

    FROM sales

    WHERE company_id=%s

    AND DATE(COALESCE(refunded_at, created_at))=%s

    AND (
    status='Возврат'
    OR COALESCE(is_refunded,FALSE)=TRUE
    )
    """,(
    company_id,
    today_str
    ))

    refunds_today=cur.fetchone()["total"] or 0

    cur.execute("""
        SELECT COALESCE(SUM(si.profit), 0) AS refunded_profit
        FROM sale_items si JOIN sales s ON s.id = si.sale_id
        WHERE s.company_id = %s
          AND (s.status = 'Возврат' OR COALESCE(s.is_refunded, FALSE) = TRUE)
          AND DATE(COALESCE(s.refunded_at, s.created_at)) = %s
    """, (company_id, today_str))
    today_profit -= cur.fetchone()["refunded_profit"] or 0
    
    cur.execute("""
    SELECT

    users.full_name,

    SUM(sales.total_amount) revenue

    FROM sales

    JOIN users
    ON users.id=sales.user_id

    WHERE sales.company_id=%s

    AND DATE(sales.created_at)=%s

    AND sales.status='Оплачено'

    GROUP BY users.full_name

    ORDER BY revenue DESC

    LIMIT 1
    """,(
    company_id,
    today_str
    ))

    best_employee=cur.fetchone()
    
    cur.execute("""
    SELECT

    sale_items.name,

    SUM(sale_items.quantity) qty

    FROM sale_items

    JOIN sales

    ON sales.id=sale_items.sale_id

    WHERE sales.company_id=%s

    AND DATE(sales.created_at)=%s

    GROUP BY sale_items.name

    ORDER BY qty DESC

    LIMIT 1
    """,(
    company_id,
    today_str
    ))

    best_item=cur.fetchone()

    # 💳 ОПЛАТЫ
    cur.execute("""
        SELECT 
            SUM(cash_amount) as cash,
            SUM(card_amount) as card,
            SUM(kaspi_amount) as kaspi
        FROM sales
        WHERE company_id = %s
          AND status IN ('Оплачено', 'Возврат')
          AND DATE(created_at) = %s
    """, (company_id, today_str))

    payments = cur.fetchone()
    cur.execute("""
        SELECT COALESCE(SUM(cash_amount), 0) cash,
               COALESCE(SUM(card_amount), 0) card,
               COALESCE(SUM(kaspi_amount), 0) kaspi
        FROM sales WHERE company_id = %s
          AND (status = 'Возврат' OR COALESCE(is_refunded, FALSE) = TRUE)
          AND DATE(COALESCE(refunded_at, created_at)) = %s
    """, (company_id, today_str))
    refunded_payments = cur.fetchone()
    payments = {
        "cash": (payments["cash"] or 0) - (refunded_payments["cash"] or 0),
        "card": (payments["card"] or 0) - (refunded_payments["card"] or 0),
        "kaspi": (payments["kaspi"] or 0) - (refunded_payments["kaspi"] or 0),
    }

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
        WITH movements AS (
            SELECT DATE(created_at) AS date, total_amount AS amount
            FROM sales WHERE company_id = %s AND status IN ('Оплачено', 'Возврат')
            UNION ALL
            SELECT DATE(COALESCE(refunded_at, created_at)), -total_amount
            FROM sales WHERE company_id = %s
              AND (status = 'Возврат' OR COALESCE(is_refunded, FALSE) = TRUE)
        )
        SELECT date, SUM(amount) AS total FROM movements
        GROUP BY date
        ORDER BY date DESC
        LIMIT 7
    """, (company_id, company_id))
    
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
        AND sales.status NOT IN ('Оплачено', 'Возврат')
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
    AND COALESCE(items.item_type, 'product') = 'product'

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
        notifications=notifications,
        sales_today=sales_today,
        average_check=average_check,
        today_profit=today_profit,
        refunds_today=refunds_today,
        best_employee=best_employee,
        best_item=best_item
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
