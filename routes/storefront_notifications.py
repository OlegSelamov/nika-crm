from flask import Blueprint, jsonify, session

from models import get_db, pool
from utils.timezone import now_kz


storefront_notifications_bp = Blueprint("storefront_notifications", __name__)


def _ensure_notifications_table(cur):
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
        CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
        ON notifications(user_id, is_read, id DESC)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_storefront_event_unique
        ON notifications(company_id, user_id, notification_type, related_id)
        WHERE notification_type IN ('storefront_order', 'storefront_booking')
    """)


def _format_money(value):
    try:
        amount = float(value or 0)
        return f"{amount:,.0f}".replace(",", " ")
    except Exception:
        return "0"


def _sync_orders(cur, company_id, user_id):
    cur.execute("""
        SELECT
            o.id,
            o.customer_name,
            o.total_amount,
            o.created_at
        FROM online_orders o
        WHERE o.company_id = %s
          AND o.created_at >= NOW() - INTERVAL '7 days'
          AND NOT EXISTS (
              SELECT 1
              FROM notifications n
              WHERE n.company_id = o.company_id
                AND n.user_id = %s
                AND n.notification_type = 'storefront_order'
                AND n.related_id = o.id
          )
        ORDER BY o.id
        LIMIT 100
    """, (company_id, user_id))

    rows = cur.fetchall()
    created = []

    for row in rows:
        order_id = row["id"]
        customer = (row.get("customer_name") or "Клиент").strip()
        amount = _format_money(row.get("total_amount"))
        created_at = row.get("created_at") or now_kz()
        message = f"Заказ #{order_id} · {customer} · {amount} ₸"

        cur.execute("""
            INSERT INTO notifications (
                company_id,
                user_id,
                notification_type,
                title,
                message,
                related_id,
                link,
                is_read,
                created_at
            )
            VALUES (%s,%s,'storefront_order',%s,%s,%s,%s,FALSE,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
        """, (
            company_id,
            user_id,
            "Новый онлайн-заказ",
            message,
            order_id,
            f"/storefront/orders?open={order_id}",
            created_at,
        ))
        if cur.fetchone():
            created.append({"type": "storefront_order", "id": order_id})

    return created


def _sync_bookings(cur, company_id, user_id):
    cur.execute("""
        SELECT
            b.id,
            b.customer_name,
            b.booking_date,
            b.booking_time,
            b.created_at,
            COALESCE(i.name, 'Услуга') AS service_name
        FROM bookings b
        LEFT JOIN items i
          ON i.id = b.item_id
         AND i.company_id = b.company_id
        WHERE b.company_id = %s
          AND b.created_at >= NOW() - INTERVAL '7 days'
          AND NOT EXISTS (
              SELECT 1
              FROM notifications n
              WHERE n.company_id = b.company_id
                AND n.user_id = %s
                AND n.notification_type = 'storefront_booking'
                AND n.related_id = b.id
          )
        ORDER BY b.id
        LIMIT 100
    """, (company_id, user_id))

    rows = cur.fetchall()
    created = []

    for row in rows:
        booking_id = row["id"]
        customer = (row.get("customer_name") or "Клиент").strip()
        service_name = (row.get("service_name") or "Услуга").strip()
        booking_date = row.get("booking_date")
        booking_time = row.get("booking_time")
        created_at = row.get("created_at") or now_kz()

        date_label = booking_date.strftime("%d.%m.%Y") if booking_date else "—"
        time_label = booking_time.strftime("%H:%M") if booking_time else "—"
        message = f"{service_name} · {customer} · {date_label} {time_label}"

        cur.execute("""
            INSERT INTO notifications (
                company_id,
                user_id,
                notification_type,
                title,
                message,
                related_id,
                link,
                is_read,
                created_at
            )
            VALUES (%s,%s,'storefront_booking',%s,%s,%s,%s,FALSE,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
        """, (
            company_id,
            user_id,
            "Новая онлайн-запись",
            message,
            booking_id,
            f"/storefront/bookings?open={booking_id}",
            created_at,
        ))
        if cur.fetchone():
            created.append({"type": "storefront_booking", "id": booking_id})

    return created


@storefront_notifications_bp.route("/api/storefront/notifications/sync", methods=["POST"])
def sync_storefront_notifications():
    user_id = session.get("user_id")
    company_id = session.get("company_id")

    if not user_id or not company_id:
        return jsonify({"success": False, "error": "Требуется авторизация"}), 401

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_notifications_table(cur)
        created = []

        # В штатной установке обе таблицы витрины уже есть. Если модуль ещё не
        # инициализирован, единичная ошибка синхронизации не должна ломать CRM.
        created.extend(_sync_orders(cur, company_id, user_id))
        created.extend(_sync_bookings(cur, company_id, user_id))

        conn.commit()
        return jsonify({
            "success": True,
            "created_count": len(created),
            "created": created,
        })
    except Exception as exc:
        conn.rollback()
        print("STOREFRONT NOTIFICATION SYNC ERROR:", exc)
        return jsonify({
            "success": False,
            "created_count": 0,
            "created": [],
            "error": "Не удалось синхронизировать уведомления",
        }), 200
    finally:
        cur.close()
        pool.putconn(conn)
