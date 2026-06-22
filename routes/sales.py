from routes.clients import format_date_ru
from flask import Blueprint, render_template, request, jsonify, redirect
from models import get_db, pool
from datetime import datetime, timedelta
from utils.timezone import now_kz
from flask import render_template
from num2words import num2words
from flask import session
import uuid
import pytz
import requests

sales_bp = Blueprint("sales", __name__)
sales_api = Blueprint("sales_api", __name__)

@sales_bp.route("/sales")
def sales():
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        SELECT sales.*, clients.full_name
        FROM sales
        LEFT JOIN clients ON sales.client_id = clients.id
        WHERE sales.company_id = %s
        ORDER BY sales.id DESC
    """, (session.get("company_id"),))

    sales = cur.fetchall()

    pool.putconn(conn)

    return render_template("sales.html", sales=sales)


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

        cur.execute("""
            INSERT INTO sales (
                client_id,
                company_id,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            client_id,
            company_id,
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
            (sale["created_at"] + timedelta(hours=5))
                .strftime("%d.%m.%Y %H:%M"),
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

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        SELECT
            sales.id,
            sales.sale_number,
            sales.created_at,
            sales.total_amount,
            sales.sale_type,
            sales.status,
            clients.full_name
        FROM sales
        LEFT JOIN clients
            ON sales.client_id = clients.id
        WHERE sales.company_id = %s
        ORDER BY sales.id DESC
        LIMIT 100
    """, (
        session.get("company_id"),
    ))

    sales = cur.fetchall()

    result = []

    for sale in sales:

        payment_type = "—"

        if sale["sale_type"] == "cash":
            payment_type = "Наличные"

        elif sale["sale_type"] == "card":
            payment_type = "Карта"

        elif sale["sale_type"] == "kaspi":
            payment_type = "Kaspi POS"

        elif sale["sale_type"] == "invoice":
            payment_type = "Счёт"

        result.append({

            "id": sale["id"],
            
            "sale_number": sale["sale_number"],

            "created_at": sale["created_at"],

            "client_name":
                sale["full_name"],

            "total":
                sale["total_amount"],

            "payment_type":
                payment_type,

            "status":
                sale["status"]

        })

    pool.putconn(conn)

    return jsonify(result)


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
    data = request.get_json()

    client_id = data.get("client_id")
    cart = data.get("cart", [])
    company_id = session.get("company_id")

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
            SELECT unit, purchase_price
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

        profit = (
            item["price"] - purchase_price
        ) * item["quantity"]

        # 🔥 обновляем profit
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

        # 🔥 списываем остатки

        cur.execute("""
            UPDATE items
            SET quantity = COALESCE(quantity, 0) - %s
            WHERE id = %s
        """, (
            item["quantity"],
            item["item_id"]
        ))
        
        # 🔥 движение склада
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
    
        # 🔥 помечаем как проведённую

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
    data = request.get_json()
    sale_id = data.get("sale_id")

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM sales WHERE id = %s AND company_id = %s",
        (sale_id, session.get("company_id"))
    )
    
    sale = cur.fetchone()

    if not sale:
        pool.putconn(conn)
        return {"success": False, "error": "Продажа не найдена"}, 404

    cur.execute("""
        UPDATE sales
        SET 
            status = 'Оплачено',
            paid_amount = total_amount,
            paid_at = %s,
            sale_type = 'invoice',
            card_amount = total_amount
        WHERE id = %s AND company_id = %s
    """, (
        now_kz(),
        sale_id,
        session.get("company_id")
    ))
    
    process_sale(conn, sale_id)

    conn.commit()
    pool.putconn(conn)

    return {"success": True}
    
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

    date_obj = sale["created_at"] + timedelta(hours=5)

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
    conn = get_db()
    
    cur = conn.cursor()

    company_id = session.get("company_id")

    # 📅 ФИЛЬТР ДАТ
    date_from = request.args.get("from")
    date_to = request.args.get("to")

    if not date_from or not date_to:
        date_to = now_kz().strftime("%Y-%m-%d")
        date_from = (now_kz() - timedelta(days=7)).strftime("%Y-%m-%d")

    # 📈 ГРАФИК
    cur.execute("""
        SELECT DATE(created_at) as date, SUM(total_amount) as total
        FROM sales
        WHERE company_id = %s
        AND sales.status = 'Оплачено'
        AND DATE(created_at) BETWEEN %s AND %s
        GROUP BY DATE(created_at)
        ORDER BY date
    """, (company_id, date_from, date_to))
    
    chart_data = cur.fetchall()

    chart_labels = [
        row["date"].strftime("%d.%m")
        for row in chart_data
    ]

    chart_values = [
        row["total"] or 0
        for row in chart_data
    ]

    # 💰 СУММЫ
    total = sum(chart_values)
    
    cur.execute("""
        SELECT SUM(profit) as profit
        FROM sale_items
        WHERE sale_id IN (
            SELECT id
            FROM sales
            WHERE company_id = %s
            AND sales.status = 'Оплачено'
            AND DATE(created_at) BETWEEN %s AND %s
        )
    """, (
        company_id,
        date_from,
        date_to
    ))
    
    profit_row = cur.fetchone()

    profit = profit_row["profit"] or 0

    # 🏆 ТОП КЛИЕНТЫ
    cur.execute("""
        SELECT clients.full_name, SUM(sales.total_amount) as total
        FROM sales
        JOIN clients ON sales.client_id = clients.id
        WHERE sales.company_id = %s
        AND sales.status = 'Оплачено'
        AND DATE(sales.created_at) BETWEEN %s AND %s
        GROUP BY clients.id
        ORDER BY total DESC
        LIMIT 5
    """, (company_id, date_from, date_to))
    
    top_clients = cur.fetchall()

    # 📦 ТОП ТОВАРЫ
    cur.execute("""
        SELECT name, SUM(total) as total
        FROM sale_items
        WHERE sale_id IN (
            SELECT id FROM sales 
            WHERE company_id = %s
            AND sales.status = 'Оплачено'
            AND DATE(created_at) BETWEEN %s AND %s
        )
        GROUP BY name
        ORDER BY total DESC
        LIMIT 5
    """, (company_id, date_from, date_to))
    
    top_items = cur.fetchall()

    # 💳 ОПЛАТЫ
    cur.execute("""
        SELECT 
            SUM(cash_amount) as cash,
            SUM(card_amount) as card,
            SUM(kaspi_amount) as kaspi
        FROM sales
        WHERE company_id = %s
        AND sales.status = 'Оплачено'
        AND DATE(created_at) BETWEEN %s AND %s
    """, (company_id, date_from, date_to))
    
    payments = cur.fetchone()
    
    today_str = now_kz().strftime("%Y-%m-%d")

    cur.execute("""
        SELECT SUM(total_amount) as total
        FROM sales
        WHERE company_id = %s
        AND sales.status = 'Оплачено'
        AND DATE(created_at) = %s
    """, (company_id, today_str))

    today = cur.fetchone()["total"] or 0
    
    pool.putconn(conn)

    return render_template(
        "analytics.html",
        chart_labels=chart_labels,
        chart_values=chart_values,
        total=total,
        top_clients=top_clients,
        top_items=top_items,
        payments=payments,
        date_from=date_from,
        date_to=date_to,
        today=today,
        profit=profit,
    )
    
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
        "SELECT * FROM items WHERE barcode = %s AND company_id = %s",
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

        cur.execute("""
            SELECT *
            FROM sales
            WHERE id = %s
            AND company_id = %s
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

        # запуск возврата

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

        # ждём ответ терминала

        refund_ok = False
        refund_transaction_id = None

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

            data_block = status_result.get("data", {})

            status = data_block.get("status")

            if status == "success":

                refund_ok = True

                refund_transaction_id = (
                    data_block.get("transactionId")
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
                UPDATE items
                SET quantity =
                    COALESCE(quantity,0) + %s
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
                VALUES (%s,%s,%s,%s,%s,%s,%s)
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

        cur.execute("""
            UPDATE sales
            SET
                status = %s,
                is_refunded = TRUE
            WHERE id = %s
        """, (
            "Возврат",
            sale_id
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "refund_transaction_id":
                refund_transaction_id
        })

    except Exception as e:

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

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            name,
            retail_price,
            gtin,
            ntin,
            type
        FROM items
        WHERE company_id = %s
        AND LOWER(name)
            LIKE LOWER(%s)
        ORDER BY name
        LIMIT 50
    """, (
        session.get("company_id"),
        f"%{q}%"
    ))

    items = cur.fetchall()

    pool.putconn(conn)

    return jsonify(items)
