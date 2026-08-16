from routes.clients import format_date_ru
from flask import Blueprint, render_template, request, jsonify, redirect, make_response, send_file, current_app
from models import get_db, pool
from datetime import datetime, timedelta
from utils.timezone import now_kz
from flask import render_template
from num2words import num2words
from flask import session
import uuid
import pytz
import requests
import json
from io import BytesIO

sales_bp = Blueprint("sales", __name__)
sales_api = Blueprint("sales_api", __name__)
refund_receipt_schema_ready = False


def ensure_refund_receipt_schema(conn):
    """Добавить хранение данных возвратного чека без отдельной миграции."""
    global refund_receipt_schema_ready

    if refund_receipt_schema_ready:
        return

    cur = conn.cursor()
    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMP WITH TIME ZONE
        """)
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN IF NOT EXISTS refund_receipt_data JSONB
        """)
        refund_receipt_schema_ready = True
    finally:
        cur.close()


def nested_value(data, *paths):
    """Вернуть первое непустое значение из нескольких путей JSON."""
    for path in paths:
        value = data
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if value not in (None, ""):
            return value
    return None

@sales_bp.route("/sales")
def sales():
    # История подгружается порциями через /api/sales/history только после
    # открытия вкладки и конкретной смены. Не читаем всю таблицу продаж при
    # каждом открытии кассы — это заметно ускоряет страницу на больших базах.
    return render_template("sales.html")


@sales_bp.route("/sales/add", methods=["POST"])
def add_sale():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sales (client_id, company_id, total_amount, paid_amount, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        request.form["client_id"],
        session.get("company_id"),
        0,
        0,
        "Новая",
        now_kz()
    ))

    conn.commit()
    pool.putconn(conn)

    return redirect("/sales")


@sales_bp.route("/sales/pay", methods=["POST"])
def pay_sale():
    data = request.get_json()
    company_id = session.get("company_id")
    user_id = session.get("user_id")
    
    print("=" * 50)
    print("COMPANY_ID =", company_id)
    print("=" * 50)

    def to_int(val):
        try:
            return int(val)
        except:
            return 0

    client_id = data.get("client_id")
    cart = data.get("cart", [])
    kaspi_transaction_id = data.get("kaspi_transaction_id")
    kaspi_method = data.get("kaspi_method")
    payment_method = data.get("payment_method", "cash")

    total = sum(
        item.get("price", 0) * item.get("qty", 1)
        for item in cart
    )

    cash = 0
    card = 0
    kaspi = 0

    if payment_method == "cash":
        cash = total

    elif payment_method == "card":
        card = total

    elif payment_method == "kaspi":
        kaspi = total

    paid = total
    status = "Оплачено"

    conn = get_db()
    
    cur = conn.cursor()

    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT COALESCE(MAX(sale_number), 0) + 1 AS next_number
            FROM sales
            WHERE company_id = %s
        """, (company_id,))

        sale_number = cur.fetchone()["next_number"]
        
        print("SALE_NUMBER =", sale_number)

        cur.execute("""
            INSERT INTO sales (
                client_id,
                company_id,
                user_id,
                sale_number,
                total_amount,
                paid_amount,
                status,
                created_at,
                sale_type,
                cash_amount,
                card_amount,
                kaspi_amount,
                kaspi_transaction_id,
                kaspi_method
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            client_id,
            company_id,
            user_id,
            sale_number,
            total,
            paid,
            status,
            now_kz(),
            payment_method,
            cash,
            card,
            kaspi,
            kaspi_transaction_id,
            kaspi_method
        ))

        sale_id = cur.fetchone()["id"]

        for item in cart:

            cur.execute(
                "SELECT unit FROM items WHERE id = %s",
                (item.get("id"),)
            )

            db_item = cur.fetchone()

            unit = (
                db_item["unit"]
                if db_item and db_item["unit"]
                else "шт"
            )

            cur.execute("""
                INSERT INTO sale_items (
                    sale_id,
                    item_id,
                    name,
                    price,
                    quantity,
                    total,
                    unit,
                    gtin,
                    ntin,
                    excise_stamp
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                sale_id,
                item.get("id"),
                item.get("name") or f"Товар #{item.get('id')}",
                item.get("price", 0),
                item.get("qty", 1),
                item.get("price", 0) * item.get("qty", 1),
                unit,
                item.get("gtin"),
                item.get("ntin"),
                item.get("excise_stamp")
            ))

        process_sale(conn, sale_id)
        
        from routes.rekassa import rekassa_sell

        rekassa_result = rekassa_sell(
            conn,
            sale_id
        )
        
        print("REKASSA RESULT:")
        print(rekassa_result)
        
        if rekassa_result.get("status") == "OK":

            cur.execute("""
                UPDATE sales
                SET
                    rekassa_ticket_id = %s,
                    rekassa_ticket_number = %s,
                    rekassa_qr = %s,
                    rekassa_shift_number = %s,
                    rekassa_status = %s,
                    rekassa_document_number = %s,
                    rekassa_rnm = %s,
                    rekassa_znm = %s
                WHERE id = %s
            """, (
                rekassa_result.get("id"),
                rekassa_result.get("ticketNumber"),
                rekassa_result.get("fdoQrCode"),
                rekassa_result.get("shiftNumber"),
                rekassa_result.get("status"),

                rekassa_result["data"]["ticket"].get("printedDocumentNumber"),

                rekassa_result["data"]["service"]["regInfo"]["kkm"].get("fnsKkmId"),

                rekassa_result["data"]["service"]["regInfo"]["kkm"].get("serialNumber"),

                sale_id
            ))
            
            print(
                "REKASSA DOC:",
                rekassa_result["data"]["ticket"].get("printedDocumentNumber")
            )

            print(
                "REKASSA RNM:",
                rekassa_result["data"]["service"]["regInfo"]["kkm"].get("fnsKkmId")
            )

            print(
                "REKASSA ZNM:",
                rekassa_result["data"]["service"]["regInfo"]["kkm"].get("serialNumber")
            )

        print("REKASSA RESULT:")
        print(rekassa_result)

        conn.commit()

    finally:
        pool.putconn(conn)

    return {"success": True, "sale_id": sale_id}


@sales_bp.route("/api/sale/<int:sale_id>")
def get_sale(sale_id):
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM sales WHERE id = %s AND company_id = %s",
        (sale_id, session.get("company_id"))
    )

    sale = cur.fetchone()

    if not sale:
        pool.putconn(conn)
        return jsonify({"error": "not found"}), 404

    cur.execute(
        "SELECT * FROM sale_items WHERE sale_id = %s",
        (sale_id,)
    )
    items = cur.fetchall()
    
    cur.execute(
        """
        SELECT
            name,
            bin,
            address
        FROM companies
        WHERE id = %s
        """,
        (sale["company_id"],)
    )

    company = cur.fetchone()

    result = {
        "id": sale["id"],
        
        "sale_number": sale.get("sale_number"),
        
        "company_name":
            company["name"] if company else "",

        "company_bin":
            company["bin"] if company else "",

        "company_address":
            company["address"] if company else "",
        "total_amount": sale["total_amount"],
        "paid_amount": sale["paid_amount"],
        "status": sale["status"],
        "sale_type": sale["sale_type"] if "sale_type" in sale.keys() else "cash",
        "created_at": sale["created_at"],
        "cash": sale["cash_amount"] if "cash_amount" in sale.keys() else 0,
        "card": sale["card_amount"] if "card_amount" in sale.keys() else 0,
        "kaspi": sale["kaspi_amount"] if "kaspi_amount" in sale.keys() else 0,
        "check_date":
            sale["created_at"].strftime("%d.%m.%Y %H:%M"),
        "kaspi_method": sale.get("kaspi_method"),
        "kaspi_transaction_id": sale.get("kaspi_transaction_id"),
        "rekassa_ticket_id": sale.get("rekassa_ticket_id"),
        "rekassa_ticket_number": sale.get("rekassa_ticket_number"),
        "rekassa_qr": sale.get("rekassa_qr"),
        "rekassa_shift_number": sale.get("rekassa_shift_number"),
        "rekassa_status": sale.get("rekassa_status"),
        "rekassa_document_number": sale.get("rekassa_document_number"),
        "rekassa_rnm": sale.get("rekassa_rnm"),
        "rekassa_znm": sale.get("rekassa_znm"),
        "items": []
    }

    for i in items:

        result["items"].append({

            "name":
                i["name"],

            "quantity":
                i["quantity"],

            "total":
                i["total"],

            "price":
                i["price"],

            "unit":
                i["unit"] if i["unit"] else "шт",

            "gtin":
                i["gtin"] if "gtin" in i.keys() else "",

            "ntin":
                i["ntin"] if "ntin" in i.keys() else ""

        })

    pool.putconn(conn)
    return jsonify(result)
    
@sales_bp.route("/api/sales/history")
def sales_history():
    all_history = request.args.get("scope") == "all"
    serial_number = (request.args.get("serial_number") or "").strip()

    try:
        page = max(int(request.args.get("page", 0)), 0)
        default_size = 50 if all_history else 100
        size = min(max(int(request.args.get("size", default_size)), 1), 100)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Некорректная страница"}), 400

    shift_number = None
    if not all_history:
        try:
            shift_number = int(request.args.get("shift_number", ""))
            if shift_number <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify([])

    conn = get_db()
    cur = conn.cursor()
    try:
        if all_history:
            cur.execute("""
                WITH journal AS (
                    SELECT
                        s.id, s.client_id, s.sale_number, s.total_amount,
                        s.sale_type, s.status, s.rekassa_shift_number,
                        s.rekassa_znm, 'sale'::TEXT AS event_type,
                        s.created_at AS event_at
                    FROM sales s
                    WHERE s.company_id = %s

                    UNION ALL

                    SELECT
                        s.id, s.client_id, s.sale_number, s.total_amount,
                        s.sale_type, s.status, s.rekassa_shift_number,
                        s.rekassa_znm, 'refund'::TEXT AS event_type,
                        COALESCE(s.refunded_at, s.created_at) AS event_at
                    FROM sales s
                    WHERE s.company_id = %s
                      AND COALESCE(s.is_refunded, FALSE) = TRUE
                )
                SELECT journal.*, clients.full_name
                FROM journal
                LEFT JOIN clients ON journal.client_id = clients.id
                ORDER BY journal.event_at DESC, journal.id DESC,
                         journal.event_type DESC
                LIMIT %s OFFSET %s
            """, (
                session.get("company_id"),
                session.get("company_id"),
                size,
                page * size,
            ))
        else:
            cur.execute("""
                WITH journal AS (
                    SELECT
                        s.id, s.client_id, s.sale_number, s.total_amount,
                        s.sale_type, s.status, s.rekassa_shift_number,
                        s.rekassa_znm, 'sale'::TEXT AS event_type,
                        s.created_at AS event_at
                    FROM sales s
                    WHERE s.company_id = %s
                      AND s.rekassa_shift_number = %s
                      AND (%s = '' OR s.rekassa_znm = %s)

                    UNION ALL

                    SELECT
                        s.id, s.client_id, s.sale_number, s.total_amount,
                        s.sale_type, s.status, s.rekassa_shift_number,
                        s.rekassa_znm, 'refund'::TEXT AS event_type,
                        COALESCE(s.refunded_at, s.created_at) AS event_at
                    FROM sales s
                    WHERE s.company_id = %s
                      AND s.rekassa_shift_number = %s
                      AND (%s = '' OR s.rekassa_znm = %s)
                      AND COALESCE(s.is_refunded, FALSE) = TRUE
                )
                SELECT journal.*, clients.full_name
                FROM journal
                LEFT JOIN clients ON journal.client_id = clients.id
                ORDER BY journal.event_at DESC, journal.id DESC,
                         journal.event_type DESC
                LIMIT %s OFFSET %s
            """, (
                session.get("company_id"),
                shift_number,
                serial_number,
                serial_number,
                session.get("company_id"),
                shift_number,
                serial_number,
                serial_number,
                size,
                page * size,
            ))

        sales = cur.fetchall()
        result = []
        for sale in sales:
            payment_type = {
                "cash": "Наличные",
                "card": "Карта",
                "kaspi": "Kaspi POS",
                "invoice": "Счёт",
            }.get(sale["sale_type"], "—")
            event_type = sale.get("event_type") or "sale"
            event_at = sale.get("event_at")
            is_refund = event_type == "refund"
            status = "Возврат" if is_refund else sale.get("status")
            if not is_refund and status == "Возврат":
                status = "Продажа"

            result.append({
                "id": sale["id"],
                "event_type": event_type,
                "sale_number": sale["sale_number"],
                "created_at": event_at,
                "event_at": event_at.isoformat() if event_at else "",
                "created_at_display": (
                    event_at.strftime("%d.%m.%Y, %H:%M") if event_at else "—"
                ),
                "client_name": sale["full_name"] or "Частное лицо",
                "total": sale["total_amount"],
                "payment_type": payment_type,
                "sale_type": sale["sale_type"],
                "status": status or "Продажа",
                "is_refunded": is_refund,
                "shift_number": sale.get("rekassa_shift_number"),
                "serial_number": sale.get("rekassa_znm") or "",
                "refund_check_available": bool(
                    is_refund and sale["sale_type"] != "invoice"
                ),
            })
        return jsonify(result)
    finally:
        cur.close()
        pool.putconn(conn)


@sales_bp.route("/api/smart-sale", methods=["POST"])
def smart_sale(payload=None):
    data = payload or request.get_json(silent=True) or {}

    client_name = (data.get("client_name") or "").strip()
    item_name = (data.get("item_name") or "").strip()

    if not client_name:
        return jsonify({"success": False, "error": "client name is empty"})

    if not item_name:
        return jsonify({"success": False, "error": "item name is empty"})

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, full_name FROM clients WHERE company_id = %s",
        (session.get("company_id"),)
    )
    clients = cur.fetchall()

    client = None
    search = (client_name or "").lower().replace("ё", "е")

    for c in clients:
        if not c:
            continue

        full_name = c["full_name"] if hasattr(c, "keys") else c[1]

        if not full_name:
            continue

        full_name_clean = full_name.lower().replace("ё", "е")

        if search in full_name_clean:
            client = c
            break

    if not client:
        pool.putconn(conn)
        return jsonify({"success": False, "error": f"client not found: {client_name}"})

    cur.execute(
        "SELECT id, retail_price, name FROM items WHERE company_id = %s",
        (session.get("company_id"),)
    )

    items = cur.fetchall()

    item = None
    search_item = (item_name or "").lower().replace("ё", "е")

    for i in items:
        if not i:
            continue

        name_i = i["name"] if hasattr(i, "keys") else i[2]

        if not name_i:
            continue

        name_clean = name_i.lower().replace("ё", "е")

        if search_item in name_clean:
            item = i
            break

    if not item:
        pool.putconn(conn)
        return jsonify({"success": False, "error": f"item not found: {item_name}"})
        
    cur.execute("""
        SELECT COALESCE(MAX(sale_number), 0) + 1 AS next_number
        FROM sales
        WHERE company_id = %s
    """, (session.get("company_id"),))

    sale_number = cur.fetchone()["next_number"]

    cur.execute("""
        INSERT INTO sales (
            client_id,
            company_id,
            sale_number,
            total_amount,
            paid_amount,
            status,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        client["id"],
        session.get("company_id"),
        sale_number,
        item["retail_price"],
        0,
        "Новая",
        now_kz()
    ))

    sale_id = cur.fetchone()["id"]

    cur.execute("""
        INSERT INTO sale_items (sale_id, item_id, name, price, quantity, total)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        sale_id,
        item["id"] if hasattr(item, "keys") else item[0],
        item["name"] if hasattr(item, "keys") else item[2],
        item["retail_price"] if hasattr(item, "keys") else item[1],
        1,
        item["retail_price"] if hasattr(item, "keys") else item[1]
    ))

    conn.commit()
    pool.putconn(conn)

    return jsonify({
        "success": True,
        "message": f"Продажа создана: {client_name} → {item_name}"
    })
    
@sales_bp.route("/sales/create-invoice", methods=["POST"])
def create_invoice():
    data = request.get_json(silent=True) or {}

    client_id = data.get("client_id")
    cart = data.get("cart", [])
    company_id = session.get("company_id")

    if not company_id:
        return jsonify({
            "success": False,
            "error": "Активная организация не выбрана"
        }), 403

    if not client_id:
        return jsonify({
            "success": False,
            "error": "Выберите клиента"
        }), 400

    if not cart:
        return jsonify({
            "success": False,
            "error": "Корзина пустая"
        }), 400

    conn = get_db()
    
    cur = conn.cursor()

    total = 0
    for i in cart:
        total += i.get("price", 0) * i.get("qty", 1)
        
    cur.execute("""
        SELECT COALESCE(MAX(sale_number), 0) + 1 AS next_number
        FROM sales
        WHERE company_id = %s
    """, (company_id,))

    sale_number = cur.fetchone()["next_number"]

    cur.execute("""
        INSERT INTO sales (
            client_id,
            company_id,
            sale_number,
            total_amount,
            paid_amount,
            status,
            created_at,
            sale_type
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        client_id,
        company_id,
        sale_number,
        total,
        0,
        "Счёт выставлен",
        now_kz(),
        "invoice"
    ))

    sale_id = cur.fetchone()["id"]

    for item in cart:
        cur.execute(
            "SELECT name, unit FROM items WHERE id = %s",
            (item.get("id"),)
        )

        db_item = cur.fetchone()

        name = db_item["name"] if db_item else "Товар"
        unit = db_item["unit"] if db_item and db_item["unit"] else "шт"

        qty = item.get("qty", 1)
        price = item.get("price", 0)

        cur.execute("""
            INSERT INTO sale_items (sale_id, item_id, name, price, quantity, total, unit)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            sale_id,
            item.get("id"),
            name,
            price,
            qty,
            price * qty,
            unit
        ))

    conn.commit()
    pool.putconn(conn)

    return jsonify({
        "success": True,
        "sale_id": sale_id
    })
    
def get_sale_data(sale_id):
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM sales WHERE id = %s AND company_id = %s",
        (sale_id, session.get("company_id"))
    )
    
    sale = cur.fetchone()

    cur.execute(
        "SELECT * FROM sale_items WHERE sale_id = %s",
        (sale_id,)
    )
    
    items = cur.fetchall()

    cur.execute(
        "SELECT * FROM clients WHERE id = %s AND company_id = %s",
        (sale["client_id"], session.get("company_id"))
    )
    client = cur.fetchone()

    pool.putconn(conn)

    return sale, items, client
    
def process_sale(conn, sale_id):

    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM sales WHERE id = %s",
        (sale_id,)
    )

    sale = cur.fetchone()

    if not sale:
        return

    if sale["is_processed"]:
        return

    cur.execute("""
        SELECT *
        FROM sale_items
        WHERE sale_id = %s
    """, (
        sale_id,
    ))

    items = cur.fetchall()

    for item in items:

        cur.execute("""
            SELECT
                unit,
                purchase_price,
                COALESCE(item_type, 'product') AS item_type
            FROM items
            WHERE id = %s
        """, (
            item["item_id"],
        ))

        db_item = cur.fetchone()

        unit = (
            db_item["unit"]
            if db_item and db_item["unit"]
            else "шт"
        )

        purchase_price = (
            db_item["purchase_price"]
            if db_item and db_item["purchase_price"]
            else 0
        )

        item_type = (
            db_item["item_type"]
            if db_item
            else "product"
        )

        profit = (
            item["price"] - purchase_price
        ) * item["quantity"]

        cur.execute("""
            UPDATE sale_items
            SET
                unit = %s,
                profit = %s
            WHERE id = %s
        """, (
            unit,
            profit,
            item["id"]
        ))

        if item_type == "product":

            cur.execute("""
                UPDATE items
                SET quantity = COALESCE(quantity, 0) - %s
                WHERE id = %s
            """, (
                item["quantity"],
                item["item_id"]
            ))

            cur.execute("""
                INSERT INTO stock_movements (
                    company_id,
                    item_id,
                    movement_type,
                    quantity,
                    price,
                    total,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                sale["company_id"],
                item["item_id"],
                "sale",
                item["quantity"],
                item["price"],
                item["total"],
                now_kz().isoformat()
            ))

    cur.execute("""
        UPDATE sales
        SET is_processed = TRUE
        WHERE id = %s
    """, (
        sale_id,
    ))

def number_to_words_kz(n):

    try:

        return num2words(
            int(n),
            lang="ru"
        ).capitalize()

    except:

        return str(n)
    
def format_fio(fio):
    if not fio:
        return ""

    parts = fio.split()

    if len(parts) == 1:
        return parts[0]

    surname = parts[0]
    initials = ""

    if len(parts) > 1:
        initials += parts[1][0] + "."
    if len(parts) > 2:
        initials += parts[2][0] + "."

    return f"{surname} {initials}"
    
@sales_bp.route("/docs/invoice/<int:sale_id>")
def invoice(sale_id):
    sale, items, client = get_sale_data(sale_id)

    if sale["sale_type"] != "invoice":
        return "Счет доступен только для безналичной продажи"

    conn = get_db()
    
    cur = conn.cursor()
    
    cur.execute(
        "SELECT * FROM companies WHERE id = %s",
        (session.get("company_id"),)
    )
    
    company = cur.fetchone()
    pool.putconn(conn)

    if not company:
        return "Активная организация не выбрана"

    date_obj = sale["created_at"]
    sale_date = date_obj.strftime("%d.%m.%Y")

    total = int(sale["total_amount"])
    total_text = number_to_words_kz(total) + " тенге 00 тиын"
    director_short = format_fio(company["director"])
    
    new_items = []

    for i in items:
        new_items.append({
            "name": i["name"],
            "quantity": i["quantity"],
            "price": i["price"],
            "total": i["total"],
            "unit": i["unit"] if i["unit"] else "шт"
        })

    return render_template(
        "docs/invoice.html",
        sale=sale,
        items=new_items,
        client=client,
        company=company,
        sale_date=sale_date,
        total_text=total_text,
        director_short=director_short,
        format_date_ru=format_date_ru
    )
    
@sales_bp.route("/sales/mark-paid", methods=["POST"])
def mark_paid():
    data = request.get_json(silent=True) or {}

    try:
        sale_id = int(data.get("sale_id"))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "Некорректный номер продажи"
        }), 400

    company_id = session.get("company_id")

    if not company_id:
        return jsonify({
            "success": False,
            "error": "Активная организация не выбрана"
        }), 403

    conn = get_db()

    try:
        cur = conn.cursor()

        # Блокируем строку на время подтверждения, чтобы двойной клик или
        # два открытых окна не провели один и тот же счёт дважды.
        cur.execute(
            """
            SELECT id, sale_type, status
            FROM sales
            WHERE id = %s AND company_id = %s
            FOR UPDATE
            """,
            (sale_id, company_id)
        )

        sale = cur.fetchone()

        if not sale:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Продажа не найдена"
            }), 404

        if sale["sale_type"] != "invoice":
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Подтвердить оплату можно только для выставленного счёта"
            }), 409

        if sale["status"] == "Возврат":
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Возвращённый счёт нельзя отметить оплаченным"
            }), 409

        if sale["status"] == "Оплачено":
            conn.rollback()
            return jsonify({
                "success": True,
                "already_paid": True,
                "status": "Оплачено"
            })

        cur.execute("""
            UPDATE sales
            SET
                status = 'Оплачено',
                paid_amount = total_amount,
                paid_at = %s,
                card_amount = total_amount
            WHERE id = %s
              AND company_id = %s
              AND sale_type = 'invoice'
        """, (
            now_kz(),
            sale_id,
            company_id
        ))

        # Склад и прибыль проводятся только после фактической оплаты счёта.
        process_sale(conn, sale_id)

        conn.commit()

        return jsonify({
            "success": True,
            "status": "Оплачено"
        })

    except Exception:
        conn.rollback()
        current_app.logger.exception(
            "Не удалось подтвердить оплату счёта %s",
            sale_id
        )
        return jsonify({
            "success": False,
            "error": "Не удалось подтвердить оплату"
        }), 500

    finally:
        pool.putconn(conn)
    
@sales_bp.route("/docs/check/<int:sale_id>")
def check(sale_id):
    sale, items, client = get_sale_data(sale_id)
    
    print("REKASSA NUMBER =", sale.get("rekassa_ticket_number"))
    print("REKASSA QR =", sale.get("rekassa_qr"))
    print("REKASSA STATUS =", sale.get("rekassa_status"))
    
    print("=" * 50)
    print("CREATED_AT:", sale["created_at"])
    print("TYPE:", type(sale["created_at"]))
    print("TZINFO:", getattr(sale["created_at"], "tzinfo", None))
    print("=" * 50)

    if sale["sale_type"] == "invoice":
        return "Чек доступен только для кассовой продажи"

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM companies WHERE id = %s",
        (session.get("company_id"),)
    )
    
    company = cur.fetchone()

    if not company:
        return "Нет компании"

    date_obj = sale["created_at"]

    check_date = date_obj.strftime("%d.%m.%Y %H:%M")
    
    new_items = []

    for i in items:

        cur.execute(
            """
            SELECT gtin, ntin, unit
            FROM items
            WHERE id = %s
            """,
            (i["item_id"],)
        )
        
        db_item = cur.fetchone()

        new_items.append({

            "name": i["name"],
            "quantity": i["quantity"],
            "price": i["price"],
            "total": i["total"],

            "unit":
                db_item["unit"]
                if db_item else "шт",

            "gtin":
                db_item["gtin"]
                if db_item else "",

            "ntin":
                db_item["ntin"]
                if db_item else ""

        })
        
    pool.putconn(conn)

    return render_template(
        "docs/check.html",
        sale=sale,
        items=new_items,
        client=client,
        company=company,
        check_date=check_date,
        cash=sale["cash_amount"]
            if "cash_amount" in sale.keys()
            else 0,

        card=sale["card_amount"]
            if "card_amount" in sale.keys()
            else 0,

        kaspi=sale["kaspi_amount"]
            if "kaspi_amount" in sale.keys()
            else 0,
    )


@sales_bp.route("/docs/refund-check/<int:sale_id>")
def refund_check(sale_id):
    conn = get_db()
    cur = conn.cursor()

    try:
        ensure_refund_receipt_schema(conn)
        conn.commit()

        cur.execute("""
            SELECT *
            FROM sales
            WHERE id = %s AND company_id = %s
        """, (sale_id, session.get("company_id")))
        sale = cur.fetchone()

        if not sale:
            return "Продажа не найдена", 404

        if sale["sale_type"] == "invoice":
            return "Для продажи по счёту чек возврата не формируется", 409

        if not sale.get("is_refunded"):
            return "Сначала оформите возврат продажи", 409

        cur.execute("""
            SELECT *
            FROM sale_items
            WHERE sale_id = %s
            ORDER BY id
        """, (sale_id,))
        items = cur.fetchall()

        cur.execute("""
            SELECT *
            FROM clients
            WHERE id = %s AND company_id = %s
        """, (sale["client_id"], session.get("company_id")))
        client = cur.fetchone()

        cur.execute(
            "SELECT * FROM companies WHERE id = %s",
            (session.get("company_id"),)
        )
        company = cur.fetchone()

        if not company:
            return "Нет компании", 404

        raw_refund_data = sale.get("refund_receipt_data") or {}
        if isinstance(raw_refund_data, str):
            try:
                raw_refund_data = json.loads(raw_refund_data)
            except (TypeError, ValueError):
                raw_refund_data = {}

        rekassa_data = raw_refund_data.get("rekassa") or {}
        refunded_at = sale.get("refunded_at") or now_kz()

        refund = {
            "ticket_id": nested_value(
                rekassa_data,
                ("id",),
                ("data", "ticket", "id")
            ),
            "ticket_number": nested_value(
                rekassa_data,
                ("ticketNumber",),
                ("data", "ticket", "ticketNumber")
            ),
            "document_number": nested_value(
                rekassa_data,
                ("printedDocumentNumber",),
                ("data", "ticket", "printedDocumentNumber")
            ),
            "shift_number": nested_value(
                rekassa_data,
                ("shiftNumber",),
                ("data", "ticket", "shiftNumber")
            ),
            "qr": nested_value(
                rekassa_data,
                ("fdoQrCode",),
                ("data", "ticket", "fdoQrCode")
            ),
            "rnm": nested_value(
                rekassa_data,
                ("rnm",),
                ("data", "service", "regInfo", "kkm", "fnsKkmId")
            ) or sale.get("rekassa_rnm"),
            "znm": nested_value(
                rekassa_data,
                ("znm",),
                ("data", "service", "regInfo", "kkm", "serialNumber")
            ) or sale.get("rekassa_znm"),
            "payment_transaction_id": raw_refund_data.get(
                "payment_refund_transaction_id"
            )
        }

        conn.commit()

        return render_template(
            "docs/refund_check.html",
            sale=sale,
            items=items,
            client=client,
            company=company,
            refund=refund,
            refund_date=refunded_at.strftime("%d.%m.%Y %H:%M"),
            original_check_date=sale["created_at"].strftime("%d.%m.%Y %H:%M")
        )
    except Exception:
        conn.rollback()
        current_app.logger.exception(
            "Не удалось сформировать чек возврата для продажи %s",
            sale_id
        )
        return "Не удалось сформировать чек возврата", 500
    finally:
        pool.putconn(conn)
    
@sales_bp.route("/docs/nakladnaya/<int:sale_id>")
def nakladnaya(sale_id):

    sale, items, client = get_sale_data(sale_id)

    # ❌ запрещаем до оплаты
    if sale["status"] != "Оплачено":
        return "Накладная доступна только после оплаты"

    conn = get_db()
    
    cur = conn.cursor()
    
    cur.execute(
        "SELECT * FROM companies WHERE id = %s",
        (session.get("company_id"),)
    )
    
    company = cur.fetchone()
    pool.putconn(conn)

    if not company:
        return "Нет компании"

    from datetime import datetime

    # дата
    date_obj = sale["created_at"]
    sale_date = date_obj.strftime("%d.%m.%Y")

    # директор
    director_short = format_fio(company["director"])

    # 🔥 HEADER
    header = {
        "sender_name": company["name"],
        "sender_address": company["address"],
        "sender_short": company["name"],
        "receiver_short": client["company_name"] or client["full_name"],
        "bin": company["bin"],
        "doc_number": sale["sale_number"],
        "doc_date": sale_date,
        "responsible": director_short,
        "transport_org": "",
        "ttn": "",
    }

    # 🔥 ТОВАРЫ
    new_items = []
    total_amount = 0

    for i in items:
        amount = i["price"] * i["quantity"]

        new_items.append({
            "name": i["name"],
            "code": i["item_id"],
            "unit": i["unit"] if i["unit"] else "шт",
            "qty_plan": i["quantity"],
            "qty_fact": i["quantity"],
            "price": i["price"],
            "amount": amount,
            "vat": 0
        })

        total_amount += amount

    # 🔥 ИТОГО
    totals = {
        "qty_plan": sum(i["quantity"] for i in items),
        "qty_fact": sum(i["quantity"] for i in items),
        "amount": total_amount,
        "vat": 0,
        "qty_words": number_to_words_kz(sum(i["quantity"] for i in items)),
        "amount_words": number_to_words_kz(total_amount) + " тенге 00 тиын"
    }

    return render_template(
        "docs/nakladnaya.html",
        header=header,
        items=new_items,
        totals=totals,
        format_date_ru=format_date_ru
    )
    
@sales_bp.route("/docs/schet-factura/<int:sale_id>")
def schet_factura(sale_id):

    sale, items, client = get_sale_data(sale_id)

    conn = get_db()
    
    cur = conn.cursor()
    
    cur.execute(
        "SELECT * FROM companies WHERE id = %s",
        (session.get("company_id"),)
    )
    
    company = cur.fetchone()
    pool.putconn(conn)

    if not company:
        return "Нет компании"
        
    payment_type = "наличный расчет"

    if sale["sale_type"] == "cash":
        # проверяем способы оплаты
        if (sale["card_amount"] or 0) > 0 or (sale["kaspi_amount"] or 0) > 0:
            payment_type = "безналичный расчет"
        else:
            payment_type = "наличный расчет"
    else:
        payment_type = "безналичный расчет"
        
    date_obj = sale["created_at"]
    sale_date = date_obj.strftime("%d.%m.%Y")

    return render_template(
        "docs/schet_factura.html",
        sale=sale,
        items=items,
        client=client,
        company=company,
        payment_type=payment_type,
        sale_date=sale_date,
        format_date_ru=format_date_ru
    )
    
@sales_bp.route("/analytics")
def analytics():
    company_id = session.get("company_id")

    if not company_id:
        return redirect("/login")

    date_from = request.args.get("from")
    date_to = request.args.get("to")

    if not date_from or not date_to:
        date_to = now_kz().strftime("%Y-%m-%d")
        date_from = (
            now_kz() - timedelta(days=7)
        ).strftime("%Y-%m-%d")

    conn = get_db()
    cur = conn.cursor()

    try:
        # =========================================================
        # ОСНОВНЫЕ ПОКАЗАТЕЛИ
        # =========================================================

        cur.execute("""
            SELECT
                COALESCE(SUM(total_amount), 0) AS revenue,
                COUNT(*) AS sales_count,
                COALESCE(AVG(total_amount), 0) AS average_check
            FROM sales
            WHERE company_id = %s
              AND status IN ('Оплачено', 'Возврат')
              AND DATE(created_at) BETWEEN %s AND %s
        """, (
            company_id,
            date_from,
            date_to
        ))

        main_stats = cur.fetchone() or {}

        gross_revenue = float(main_stats.get("revenue") or 0)
        total = gross_revenue
        sales_count = int(main_stats.get("sales_count") or 0)
        average_check = float(main_stats.get("average_check") or 0)

        # =========================================================
        # ПРИБЫЛЬ
        # =========================================================

        cur.execute("""
            SELECT
                COALESCE(SUM(si.profit), 0) AS profit
            FROM sale_items si
            JOIN sales s
                ON s.id = si.sale_id
            WHERE s.company_id = %s
              AND s.status IN ('Оплачено', 'Возврат')
              AND DATE(s.created_at) BETWEEN %s AND %s
        """, (
            company_id,
            date_from,
            date_to
        ))

        profit_row = cur.fetchone() or {}
        gross_profit = float(profit_row.get("profit") or 0)
        profit = gross_profit

        # Пока отдельные расходы в этом роуте не подключены
        purchase_total = 0
        salary_total = 0
        taxes_total = 0
        expenses_total = 0
        expense_categories = []

        cur.execute("""
            SELECT COALESCE(category, 'Прочее') AS category,
                   COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE company_id = %s AND date BETWEEN %s AND %s
            GROUP BY COALESCE(category, 'Прочее')
            ORDER BY total DESC
        """, (company_id, date_from, date_to))
        expense_categories = cur.fetchall() or []
        expenses_total = sum(float(row.get("total") or 0) for row in expense_categories)
        for row in expense_categories:
            category = str(row.get("category") or "").lower()
            amount = float(row.get("total") or 0)
            if "закуп" in category or "товар" in category:
                purchase_total += amount
            elif "зарп" in category or "оклад" in category:
                salary_total += amount
            elif "налог" in category:
                taxes_total += amount

        # =========================================================
        # ВОЗВРАТЫ
        # =========================================================

        cur.execute("""
            SELECT
                COUNT(*) AS returns_count,
                COALESCE(SUM(total_amount), 0) AS returns_total
            FROM sales
            WHERE company_id = %s
              AND (
                    status = 'Возврат'
                    OR COALESCE(is_refunded, FALSE) = TRUE
                  )
              AND DATE(COALESCE(refunded_at, created_at)) BETWEEN %s AND %s
        """, (
            company_id,
            date_from,
            date_to
        ))

        returns_row = cur.fetchone() or {}

        returns_count = int(
            returns_row.get("returns_count") or 0
        )

        returns_total = float(
            returns_row.get("returns_total") or 0
        )

        cur.execute("""
            SELECT COALESCE(SUM(si.profit), 0) AS refunded_profit
            FROM sale_items si JOIN sales s ON s.id = si.sale_id
            WHERE s.company_id = %s
              AND (s.status = 'Возврат' OR COALESCE(s.is_refunded, FALSE) = TRUE)
              AND DATE(COALESCE(s.refunded_at, s.created_at)) BETWEEN %s AND %s
        """, (company_id, date_from, date_to))
        refunded_profit = float((cur.fetchone() or {}).get("refunded_profit") or 0)
        total = gross_revenue - returns_total
        gross_profit = gross_profit - refunded_profit
        profit = gross_profit - expenses_total
        margin_percent = (profit / total * 100) if total > 0 else 0

        # =========================================================
        # СПОСОБЫ ОПЛАТЫ
        # =========================================================

        cur.execute("""
            SELECT
                COALESCE(SUM(cash_amount), 0) AS cash,
                COALESCE(SUM(card_amount), 0) AS card,
                COALESCE(SUM(kaspi_amount), 0) AS kaspi
            FROM sales
            WHERE company_id = %s
              AND status IN ('Оплачено', 'Возврат')
              AND DATE(created_at) BETWEEN %s AND %s
        """, (
            company_id,
            date_from,
            date_to
        ))

        payments_row = cur.fetchone() or {}

        payments = {
            "cash": float(payments_row.get("cash") or 0),
            "card": float(payments_row.get("card") or 0),
            "kaspi": float(payments_row.get("kaspi") or 0)
        }

        cur.execute("""
            SELECT COALESCE(SUM(cash_amount), 0) AS cash,
                   COALESCE(SUM(card_amount), 0) AS card,
                   COALESCE(SUM(kaspi_amount), 0) AS kaspi
            FROM sales
            WHERE company_id = %s
              AND (status = 'Возврат' OR COALESCE(is_refunded, FALSE) = TRUE)
              AND DATE(COALESCE(refunded_at, created_at)) BETWEEN %s AND %s
        """, (company_id, date_from, date_to))
        refunded_payments = cur.fetchone() or {}
        for key in ("cash", "card", "kaspi"):
            payments[key] -= float(refunded_payments.get(key) or 0)

        # =========================================================
        # ГРАФИК ВЫРУЧКИ
        # =========================================================

        cur.execute("""
            WITH movements AS (
                SELECT DATE(created_at) AS date, total_amount AS amount
                FROM sales
                WHERE company_id = %s AND status IN ('Оплачено', 'Возврат')
                  AND DATE(created_at) BETWEEN %s AND %s
                UNION ALL
                SELECT DATE(COALESCE(refunded_at, created_at)), -total_amount
                FROM sales
                WHERE company_id = %s
                  AND (status = 'Возврат' OR COALESCE(is_refunded, FALSE) = TRUE)
                  AND DATE(COALESCE(refunded_at, created_at)) BETWEEN %s AND %s
            )
            SELECT date, COALESCE(SUM(amount), 0) AS total
            FROM movements GROUP BY date ORDER BY date
        """, (
            company_id,
            date_from,
            date_to,
            company_id,
            date_from,
            date_to
        ))

        chart_rows = cur.fetchall() or []

        chart_labels = [
            row["date"].strftime("%d.%m")
            for row in chart_rows
        ]

        chart_values = [
            float(row["total"] or 0)
            for row in chart_rows
        ]

        # =========================================================
        # ГРАФИК ПРИБЫЛИ
        # =========================================================

        cur.execute("""
            SELECT
                DATE(s.created_at) AS date,
                COALESCE(SUM(si.profit), 0) AS total
            FROM sales s
            LEFT JOIN sale_items si
                ON si.sale_id = s.id
            WHERE s.company_id = %s
              AND s.status = 'Оплачено'
              AND DATE(s.created_at) BETWEEN %s AND %s
            GROUP BY DATE(s.created_at)
            ORDER BY DATE(s.created_at)
        """, (
            company_id,
            date_from,
            date_to
        ))

        profit_rows = cur.fetchall() or []

        profit_by_date = {
            row["date"]: float(row["total"] or 0)
            for row in profit_rows
        }

        revenue_dates = [
            row["date"]
            for row in chart_rows
        ]

        profit_chart_values = [
            profit_by_date.get(date, 0)
            for date in revenue_dates
        ]

        cur.execute("""
            SELECT date, COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE company_id = %s AND date BETWEEN %s AND %s
            GROUP BY date
        """, (company_id, date_from, date_to))
        expenses_by_date = {
            row["date"]: float(row["total"] or 0)
            for row in (cur.fetchall() or [])
        }
        expense_chart_values = [expenses_by_date.get(day, 0) for day in revenue_dates]

        # =========================================================
        # ТОП ТОВАРОВ
        # =========================================================

        cur.execute("""
            SELECT
                si.name,
                COALESCE(SUM(si.quantity), 0) AS quantity,
                COALESCE(SUM(si.total), 0) AS total
            FROM sale_items si
            JOIN sales s
                ON s.id = si.sale_id
            WHERE s.company_id = %s
              AND s.status = 'Оплачено'
              AND DATE(s.created_at) BETWEEN %s AND %s
            GROUP BY si.name
            ORDER BY total DESC
            LIMIT 5
        """, (
            company_id,
            date_from,
            date_to
        ))

        top_items_rows = cur.fetchall() or []

        top_items = [
            {
                "name": row.get("name") or "Без названия",
                "quantity": float(row.get("quantity") or 0),
                "total": float(row.get("total") or 0)
            }
            for row in top_items_rows
        ]

        # =========================================================
        # ТОП КЛИЕНТОВ
        # =========================================================

        cur.execute("""
            SELECT
                COALESCE(c.full_name, 'Частное лицо') AS full_name,
                COUNT(s.id) AS sales_count,
                COALESCE(SUM(s.total_amount), 0) AS total
            FROM sales s
            LEFT JOIN clients c
                ON c.id = s.client_id
            WHERE s.company_id = %s
              AND s.status = 'Оплачено'
              AND DATE(s.created_at) BETWEEN %s AND %s
            GROUP BY
                c.id,
                c.full_name
            ORDER BY total DESC
            LIMIT 5
        """, (
            company_id,
            date_from,
            date_to
        ))

        top_clients_rows = cur.fetchall() or []

        top_clients = [
            {
                "full_name": row.get("full_name") or "Частное лицо",
                "sales_count": int(row.get("sales_count") or 0),
                "total": float(row.get("total") or 0)
            }
            for row in top_clients_rows
        ]

        # =========================================================
        # КОЛИЧЕСТВО КЛИЕНТОВ
        # =========================================================

        cur.execute("""
            SELECT COUNT(*) AS clients_count
            FROM clients
            WHERE company_id = %s
        """, (company_id,))

        clients_row = cur.fetchone() or {}

        clients_count = int(
            clients_row.get("clients_count") or 0
        )

        # Временно, пока дата регистрации клиента отдельно не считается
        new_clients = 0

        # =========================================================
        # АНАЛИТИКА СОТРУДНИКОВ
        # =========================================================

        cur.execute("""
            SELECT
                u.id,
                u.full_name,
                u.username,
                u.role,
                COALESCE(u.percent_rate, 0) AS percent_rate,

                COUNT(s.id) FILTER (
                    WHERE s.status = 'Оплачено'
                ) AS sales_count,

                COALESCE(
                    SUM(s.total_amount) FILTER (
                        WHERE s.status = 'Оплачено'
                    ),
                    0
                ) AS revenue,

                COALESCE(
                    AVG(s.total_amount) FILTER (
                        WHERE s.status = 'Оплачено'
                    ),
                    0
                ) AS average_check,

                COUNT(s.id) FILTER (
                    WHERE s.status = 'Возврат'
                       OR COALESCE(s.is_refunded, FALSE) = TRUE
                ) AS refund_count

            FROM users u

            LEFT JOIN sales s
                ON s.user_id = u.id
               AND s.company_id = %s
               AND DATE(s.created_at) BETWEEN %s AND %s

            WHERE u.company_id = %s

            GROUP BY
                u.id,
                u.full_name,
                u.username,
                u.role,
                u.percent_rate

            ORDER BY revenue DESC, u.id
        """, (
            company_id,
            date_from,
            date_to,
            company_id
        ))

        employee_rows = cur.fetchall() or []

        employee_stats = []

        max_employee_revenue = max(
            [
                float(row.get("revenue") or 0)
                for row in employee_rows
            ],
            default=0
        )

        for row in employee_rows:
            employee_revenue = float(
                row.get("revenue") or 0
            )

            percent_rate = float(
                row.get("percent_rate") or 0
            )

            reward = (
                employee_revenue
                * percent_rate
                / 100
            )

            progress_percent = (
                employee_revenue
                / max_employee_revenue
                * 100
                if max_employee_revenue > 0
                else 0
            )

            employee_stats.append({
                "id": row.get("id"),
                "full_name": row.get("full_name"),
                "username": row.get("username"),
                "role": row.get("role") or "employee",
                "percent_rate": percent_rate,
                "sales_count": int(
                    row.get("sales_count") or 0
                ),
                "revenue": employee_revenue,
                "average_check": float(
                    row.get("average_check") or 0
                ),
                "refund_count": int(
                    row.get("refund_count") or 0
                ),
                "reward": reward,
                "progress_percent": round(
                    progress_percent,
                    1
                )
            })

        # =========================================================
        # ВЫРУЧКА ЗА СЕГОДНЯ
        # =========================================================

        today_str = now_kz().strftime("%Y-%m-%d")

        cur.execute("""
            SELECT
                COALESCE(SUM(total_amount), 0) AS total
            FROM sales
            WHERE company_id = %s
              AND status = 'Оплачено'
              AND DATE(created_at) = %s
        """, (
            company_id,
            today_str
        ))

        today_row = cur.fetchone() or {}
        today = float(today_row.get("total") or 0)

        return render_template(
            "analytics.html",

            date_from=date_from,
            date_to=date_to,

            total=total,
            gross_revenue=gross_revenue,
            profit=profit,
            gross_profit=gross_profit,

            sales_count=sales_count,
            average_check=average_check,

            payments=payments,

            returns_count=returns_count,
            returns_total=returns_total,

            expenses_total=expenses_total,
            purchase_total=purchase_total,
            salary_total=salary_total,
            taxes_total=taxes_total,
            expense_categories=expense_categories,

            margin_percent=margin_percent,

            clients_count=clients_count,
            new_clients=new_clients,

            chart_labels=chart_labels,
            chart_values=chart_values,
            profit_chart_values=profit_chart_values,
            expense_chart_values=expense_chart_values,

            top_items=top_items,
            top_clients=top_clients,
            employee_stats=employee_stats,

            today=today
        )

    except Exception:
        conn.rollback()

        import traceback
        traceback.print_exc()

        return "Не удалось загрузить аналитику", 500

    finally:
        cur.close()
        pool.putconn(conn)
    
@sales_bp.route("/analytics/employee/<int:user_id>")
def employee_analytics(user_id):

    if not session.get("user_id"):
        return redirect("/login")

    company_id = session.get("company_id")

    date_from = request.args.get("from")
    date_to = request.args.get("to")

    if not date_from or not date_to:
        date_to = now_kz().strftime("%Y-%m-%d")
        date_from = (
            now_kz() - timedelta(days=30)
        ).strftime("%Y-%m-%d")

    conn = get_db()
    cur = conn.cursor()

    try:

        # Данные сотрудника
        cur.execute("""
            SELECT
                id,
                full_name,
                username,
                role,
                phone,
                created_at,
                COALESCE(percent_rate, 0) AS percent_rate
            FROM users
            WHERE id = %s
            AND company_id = %s
        """, (
            user_id,
            company_id
        ))

        employee = cur.fetchone()

        if not employee:
            return "Сотрудник не найден", 404

        # Общие показатели сотрудника
        cur.execute("""
            SELECT

                COUNT(*) FILTER (
                    WHERE status = 'Оплачено'
                ) AS sales_count,

                COALESCE(
                    SUM(total_amount) FILTER (
                        WHERE status = 'Оплачено'
                    ),
                    0
                ) AS revenue,

                COALESCE(
                    AVG(total_amount) FILTER (
                        WHERE status = 'Оплачено'
                    ),
                    0
                ) AS average_check,

                COUNT(*) FILTER (
                    WHERE status = 'Возврат'
                    OR COALESCE(is_refunded, FALSE) = TRUE
                ) AS refund_count,

                COALESCE(
                    SUM(total_amount) FILTER (
                        WHERE status = 'Возврат'
                        OR COALESCE(is_refunded, FALSE) = TRUE
                    ),
                    0
                ) AS refund_total

            FROM sales

            WHERE company_id = %s
            AND user_id = %s
            AND DATE(created_at) BETWEEN %s AND %s
        """, (
            company_id,
            user_id,
            date_from,
            date_to
        ))

        stats = cur.fetchone()

        revenue = float(stats["revenue"] or 0)
        percent_rate = float(employee["percent_rate"] or 0)

        reward = revenue * percent_rate / 100

        # График сотрудника
        cur.execute("""
            SELECT
                DATE(created_at) AS date,
                COALESCE(SUM(total_amount), 0) AS total
            FROM sales
            WHERE company_id = %s
            AND user_id = %s
            AND status = 'Оплачено'
            AND DATE(created_at) BETWEEN %s AND %s
            GROUP BY DATE(created_at)
            ORDER BY date
        """, (
            company_id,
            user_id,
            date_from,
            date_to
        ))

        chart_rows = cur.fetchall()

        employee_chart_labels = [
            row["date"].strftime("%d.%m")
            for row in chart_rows
        ]

        employee_chart_values = [
            float(row["total"] or 0)
            for row in chart_rows
        ]

        # Лучшие товары
        cur.execute("""
            SELECT
                sale_items.name,
                COALESCE(SUM(sale_items.quantity), 0) AS quantity,
                COALESCE(SUM(sale_items.total), 0) AS total
            FROM sale_items

            JOIN sales
                ON sales.id = sale_items.sale_id

            WHERE sales.company_id = %s
            AND sales.user_id = %s
            AND sales.status = 'Оплачено'
            AND DATE(sales.created_at) BETWEEN %s AND %s

            GROUP BY sale_items.name

            ORDER BY total DESC

            LIMIT 10
        """, (
            company_id,
            user_id,
            date_from,
            date_to
        ))

        top_employee_items = cur.fetchall()

        # Последние продажи
        cur.execute("""
            SELECT
                id,
                sale_number,
                total_amount,
                sale_type,
                status,
                created_at
            FROM sales
            WHERE company_id = %s
            AND user_id = %s
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY id DESC
            LIMIT 50
        """, (
            company_id,
            user_id,
            date_from,
            date_to
        ))

        recent_sales = cur.fetchall()

        return render_template(
            "employee_analytics.html",
            employee=employee,
            stats=stats,
            reward=reward,
            top_employee_items=top_employee_items,
            recent_sales=recent_sales,
            employee_chart_labels=employee_chart_labels,
            employee_chart_values=employee_chart_values,
            date_from=date_from,
            date_to=date_to
        )

    finally:
        cur.close()
        pool.putconn(conn)
    
@sales_bp.route("/api/analytics")
def analytics_api():
    
    print("DATE FROM =", request.args.get("date_from"))
    print("DATE TO =", request.args.get("date_to"))

    conn = get_db()
    cur = conn.cursor()

    company_id = session.get("company_id")

    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    if not date_from or not date_to:

        date_to = now_kz().strftime("%Y-%m-%d")

        date_from = (
            now_kz() - timedelta(days=30)
        ).strftime("%Y-%m-%d")

    cur.execute("""
        SELECT
            COALESCE(SUM(total_amount),0) as total
        FROM sales
        WHERE company_id = %s
        AND status = 'Оплачено'
        AND DATE(created_at)
            BETWEEN %s AND %s
    """, (
        company_id,
        date_from,
        date_to
    ))

    revenue = cur.fetchone()["total"] or 0

    cur.execute("""
        SELECT
            COALESCE(SUM(profit),0) as profit
        FROM sale_items
        WHERE sale_id IN (

            SELECT id
            FROM sales
            WHERE company_id = %s
            AND status = 'Оплачено'
            AND DATE(created_at)
                BETWEEN %s AND %s

        )
    """, (
        company_id,
        date_from,
        date_to
    ))

    profit = cur.fetchone()["profit"] or 0

    cur.execute("""
        SELECT COUNT(*) as count
        FROM sales
        WHERE company_id = %s
        AND status = 'Оплачено'
        AND DATE(created_at)
            BETWEEN %s AND %s
    """, (
        company_id,
        date_from,
        date_to
    ))

    sales_count = cur.fetchone()["count"] or 0

    cur.execute("""
        SELECT
            COALESCE(
                AVG(total_amount),
                0
            ) as avg_check
        FROM sales
        WHERE company_id = %s
        AND status = 'Оплачено'
        AND DATE(created_at)
            BETWEEN %s AND %s
    """, (
        company_id,
        date_from,
        date_to
    ))

    average_check = (
        cur.fetchone()["avg_check"] or 0
    )

    cur.execute("""
        SELECT
            COALESCE(SUM(cash_amount),0) as cash,
            COALESCE(SUM(card_amount),0) as card,
            COALESCE(SUM(kaspi_amount),0) as kaspi
        FROM sales
        WHERE company_id = %s
        AND status = 'Оплачено'
        AND DATE(created_at)
            BETWEEN %s AND %s
    """, (
        company_id,
        date_from,
        date_to
    ))

    payments = cur.fetchone()

    cur.execute("""
        SELECT
            name,
            SUM(total) as total
        FROM sale_items
        WHERE sale_id IN (
            SELECT id
            FROM sales
            WHERE company_id = %s
            AND status = 'Оплачено'
            AND DATE(created_at)
                BETWEEN %s AND %s
        )
        GROUP BY name
        ORDER BY total DESC
        LIMIT 10
    """, (
        company_id,
        date_from,
        date_to
    ))

    top_items = cur.fetchall()

    cur.execute("""
        SELECT
            clients.full_name,
            SUM(sales.total_amount) as total
        FROM sales
        JOIN clients
            ON sales.client_id = clients.id
        WHERE sales.company_id = %s
        AND sales.status = 'Оплачено'
        AND DATE(sales.created_at)
            BETWEEN %s AND %s
        GROUP BY clients.id
        ORDER BY total DESC
        LIMIT 10
    """, (
        company_id,
        date_from,
        date_to
    ))

    top_clients = cur.fetchall()

    pool.putconn(conn)

    return jsonify({

        "revenue": revenue,

        "profit": profit,

        "sales_count": sales_count,

        "average_check": average_check,

        "cash": payments["cash"],

        "card": payments["card"],

        "kaspi": payments["kaspi"],

        "top_items": top_items,

        "top_clients": top_clients

    })
    
@sales_bp.route("/api/barcode", methods=["POST"])
def barcode():
    data = request.get_json()
    code = data.get("barcode")

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM items WHERE barcode = %s AND company_id = %s LIMIT 1",
        (code, session.get("company_id"))
    )

    item = cur.fetchone()

    pool.putconn(conn)

    if item:
        return {
            "found": True,
            "id": item["id"],
            "name": item["name"],
            "price": item["retail_price"],
            "unit": item.get("unit"),
            "gtin": item.get("gtin"),
            "ntin": item.get("ntin"),
            "is_marked": item.get("is_marked")
        }

    return {"found": False}
    
@sales_bp.route("/api/add-item", methods=["POST"])
def add_item_api():
    data = request.get_json()

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO items (
            name,
            retail_price,
            barcode,
            company_id
        )
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (
        data["name"],
        data["price"],
        data["barcode"],
        session.get("company_id")
    ))

    item_id = cur.fetchone()["id"]
    
    conn.commit()

    cur.execute(
        "SELECT * FROM items WHERE id = %s",
        (item_id,)
    )

    item = cur.fetchone()

    pool.putconn(conn)

    return {
        "id": item["id"],
        "name": item["name"],
        "price": item["retail_price"]
    }
    
# 👉 хранение последнего скана
last_barcode = None

@sales_bp.route("/api/scan", methods=["POST"])
def scan_barcode():
    global last_barcode
    data = request.json
    last_barcode = data.get("code")
    return {"success": True}

@sales_bp.route("/api/get-scan")
def get_scan():
    global last_barcode
    code = last_barcode
    last_barcode = None
    return {"code": code}
 
active_sessions = {}

@sales_bp.route("/api/create-session")
def create_session():
    session_id = str(uuid.uuid4())[:8]
    active_sessions[session_id] = None
    return {"session": session_id}

@sales_bp.route("/api/scan/<session_id>", methods=["POST"])
def scan_with_session(session_id):
    data = request.json
    code = data.get("code")

    if session_id in active_sessions:
        active_sessions[session_id] = code

    return {"ok": True}

@sales_bp.route("/api/get-scan/<session_id>")
def get_scan_session(session_id):
    code = active_sessions.get(session_id)
    active_sessions[session_id] = None
    return {"code": code}
    
@sales_bp.route("/scanner")
def scanner_page():
    return render_template("scanner.html")
    
@sales_bp.route("/docs/act/<int:sale_id>")
def act(sale_id):

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM sales WHERE id = %s",
        (sale_id,)
    )
    sale = cur.fetchone()

    cur.execute(
        "SELECT * FROM sale_items WHERE sale_id = %s",
        (sale_id,)
    )
    items = cur.fetchall()

    cur.execute(
        "SELECT * FROM companies WHERE id = %s",
        (session.get("company_id"),)
    )
    company = cur.fetchone()

    cur.execute(
        "SELECT * FROM clients WHERE id = %s",
        (sale["client_id"],)
    )
    client = cur.fetchone()

    sale = dict(sale)
    company = dict(company)
    client = dict(client)

    total = sum(item["total"] or 0 for item in items)
    
    pool.putconn(conn)

    return render_template(
        "docs/act.html",
        sale=sale,
        items=items,
        company=company,
        client=client,
        total=total,
        date=now_kz().strftime("%d.%m.%Y"),
        format_date_ru=format_date_ru
    )


@sales_bp.route("/docs/pdf/<document_type>/<int:sale_id>")
def document_pdf(document_type, sale_id):
    """Сформировать PDF из того же серверного шаблона, что открыт в модалке."""
    documents = {
        "check": (check, "check"),
        "refund-check": (refund_check, "refund-check"),
        "invoice": (invoice, "schet-na-oplatu"),
        "nakladnaya": (nakladnaya, "nakladnaya"),
        "schet-factura": (schet_factura, "schet-factura"),
        "act": (act, "akt-vypolnennyh-rabot"),
    }

    document = documents.get(document_type)
    if not document:
        return jsonify({"error": "Неизвестный тип документа"}), 404

    try:
        from weasyprint import HTML
    except ImportError:
        return jsonify({
            "error": "На сервере не установлен модуль формирования PDF (WeasyPrint)"
        }), 503

    render_document, filename_prefix = document

    try:
        rendered = make_response(render_document(sale_id))
        if rendered.status_code >= 400:
            return rendered

        html = rendered.get_data(as_text=True)
        pdf = HTML(
            string=html,
            base_url=request.url_root,
            media_type="print",
        ).write_pdf()

        return send_file(
            BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{filename_prefix}-{sale_id}.pdf",
            max_age=0,
        )
    except Exception:
        current_app.logger.exception(
            "Не удалось сформировать PDF %s для продажи %s",
            document_type,
            sale_id,
        )
        return jsonify({"error": "Не удалось сформировать PDF документа"}), 500
    
@sales_bp.route("/quick-add-item", methods=["POST"])
def quick_add_item():

    data = request.json

    db = get_db()

    cur = db.cursor()

    cur.execute("""
        INSERT INTO items (
            name,
            retail_price,
            purchase_price,
            barcode,
            quantity,
            unit,
            category,
            gtin,
            ntin,
            is_marked,
            company_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        data.get("name"),
        data.get("retail_price", 0),
        data.get("purchase_price", 0),
        data.get("barcode"),
        0,
        data.get("unit", "шт"),
        data.get("category"),
        data.get("gtin", ""),
        data.get("ntin", ""),
        data.get("is_marked", False),
        session.get("company_id")
    ))

    item_id = cur.fetchone()["id"]

    db.commit()
    
    pool.putconn(db)

    return jsonify({

        "success": True,

        "item": {

            "id": item_id,

            "name": data.get("name"),

            "price":
                float(
                    data.get(
                        "retail_price",
                        0
                    )
                )

        }

    })
    
@sales_bp.route("/sales/refund/<int:sale_id>", methods=["POST"])
def refund_sale(sale_id):

    import time

    conn = get_db()
    cur = conn.cursor()

    try:

        ensure_refund_receipt_schema(conn)
        conn.commit()

        cur.execute("""
            SELECT *
            FROM sales
            WHERE id = %s
            AND company_id = %s
            FOR UPDATE
        """, (
            sale_id,
            session.get("company_id")
        ))

        sale = cur.fetchone()

        if not sale:
            return jsonify({
                "success": False,
                "error": "Продажа не найдена"
            })

        if sale.get("is_refunded"):
            return jsonify({
                "success": False,
                "error": "Продажа уже возвращена"
            })

        refund_transaction_id = None
        rekassa_refund_result = None

        if sale["sale_type"] == "kaspi":

            transaction_id = sale.get(
                "kaspi_transaction_id"
            )

            if not transaction_id:
                return jsonify({
                    "success": False,
                    "error": "Нет transactionId"
                })

            amount = int(sale["total_amount"])

            method = sale.get("kaspi_method") or "qr"

            refund_response = requests.get(
                "http://10.149.133.105:8080/v2/refund",
                params={
                    "transactionId": transaction_id,
                    "amount": amount,
                    "method": method
                },
                timeout=15
            )

            refund_result = refund_response.json()

            if refund_result.get("statusCode") != 0:
                return jsonify({
                    "success": False,
                    "error": refund_result
                })

            process_id = refund_result["data"]["processId"]

            refund_ok = False

            for _ in range(30):

                time.sleep(2)

                status_response = requests.get(
                    "http://10.149.133.105:8080/v2/status",
                    params={
                        "processId": process_id
                    },
                    timeout=15
                )

                status_result = status_response.json()

                data_block = status_result.get(
                    "data",
                    {}
                )

                status = data_block.get("status")

                if status == "success":

                    refund_ok = True

                    refund_transaction_id = (
                        data_block.get(
                            "transactionId"
                        )
                    )

                    break

                if status == "fail":

                    return jsonify({
                        "success": False,
                        "error": "Возврат отменён или отклонён"
                    })

            if not refund_ok:

                return jsonify({
                    "success": False,
                    "error": "Истекло время ожидания возврата"
                })
                
        if sale.get("rekassa_ticket_id"):

            from routes.rekassa import rekassa_refund

            rekassa_refund_result = rekassa_refund(
                conn,
                sale_id
            )

            print("REKASSA REFUND RESULT:")
            print(rekassa_refund_result)

            if rekassa_refund_result.get("status") != "OK":
                print("REKASSA REFUND ERROR:")
                print(rekassa_refund_result)

                return jsonify({
                    "success": False,
                    "error": str(rekassa_refund_result)
                })

        # возвращаем товар на склад

        cur.execute("""
            SELECT *
            FROM sale_items
            WHERE sale_id = %s
        """, (
            sale_id,
        ))

        items = cur.fetchall()

        for item in items:

            cur.execute("""
                SELECT COALESCE(item_type, 'product') AS item_type
                FROM items
                WHERE id = %s
            """, (
                item["item_id"],
            ))

            db_item = cur.fetchone()
            item_type = db_item["item_type"] if db_item else "product"

            if item_type == "product":

                cur.execute("""
                    UPDATE items
                    SET quantity = COALESCE(quantity, 0) + %s
                    WHERE id = %s
                """, (
                    item["quantity"],
                    item["item_id"]
                ))

                cur.execute("""
                    INSERT INTO stock_movements (
                        company_id,
                        item_id,
                        movement_type,
                        quantity,
                        price,
                        total,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    sale["company_id"],
                    item["item_id"],
                    "refund",
                    item["quantity"],
                    item["price"],
                    item["total"],
                    now_kz().isoformat()
                ))

        # обновляем продажу

        refund_receipt_data = {
            "payment_refund_transaction_id": refund_transaction_id,
            "rekassa": rekassa_refund_result or {}
        }
        refunded_at = now_kz()

        cur.execute("""
            UPDATE sales
            SET
                status = %s,
                is_refunded = TRUE,
                refunded_at = %s,
                refund_receipt_data = %s::jsonb
            WHERE id = %s
        """, (
            "Возврат",
            refunded_at,
            json.dumps(refund_receipt_data, ensure_ascii=False, default=str),
            sale_id
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "refund_check_available": sale["sale_type"] != "invoice",
            "refund_check_url": (
                f"/docs/refund-check/{sale_id}"
                if sale["sale_type"] != "invoice"
                else None
            ),
            "refund_transaction_id":
                refund_transaction_id
        })

    except Exception as e:

        import traceback
        traceback.print_exc()

        conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        })

    finally:

        pool.putconn(conn)
        
@sales_bp.route("/api/gtin", methods=["POST"])
def find_by_gtin():

    data = request.get_json()

    gtin = data.get("gtin")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM items
        WHERE gtin = %s
        AND company_id = %s
    """, (
        gtin,
        session.get("company_id")
    ))

    item = cur.fetchone()

    pool.putconn(conn)

    if not item:
        return {"found": False}

    return {
        "found": True,
        "id": item["id"],
        "name": item["name"],
        "price": item["retail_price"],
        "gtin": item["gtin"],
        "ntin": item["ntin"]
    }
    
@sales_bp.route("/api/items/search")
def search_items():
    q = request.args.get("q", "").strip()

    if len(q) < 2:
        return jsonify({"items": [], "has_more": False})

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            name,
            retail_price,
            barcode,
            unit,
            gtin,
            ntin,
            COALESCE(item_type, 'product') AS item_type
        FROM items
        WHERE company_id = %s
          AND (
              name ILIKE %s
              OR COALESCE(barcode, '') LIKE %s
          )
        ORDER BY
            CASE
                WHEN barcode = %s THEN 0
                WHEN name ILIKE %s THEN 1
                WHEN name ILIKE %s THEN 2
                ELSE 3
            END,
            name
        LIMIT 31
    """, (
        session.get("company_id"),
        f"%{q}%",
        f"{q}%",
        q,
        q,
        f"{q}%"
    ))

    items = cur.fetchall()

    pool.putconn(conn)

    has_more = len(items) > 30

    return jsonify({
        "items": items[:30],
        "has_more": has_more
    })
