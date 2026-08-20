from datetime import datetime, date, timedelta
import re
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, session, url_for, jsonify
from models import get_db, pool
from utils.timezone import now_kz

storefront_bp = Blueprint("storefront", __name__, url_prefix="/s")


# Фактический остаток считается по движениям склада. Поле items.quantity
# может отставать после прихода или списания, поэтому его не используем
# в публичной витрине и при проверке корзины.
STOREFRONT_STOCK_SQL = """
    COALESCE((
        SELECT SUM(
            CASE
                WHEN sm.movement_type IN ('income', 'refund') THEN sm.quantity
                WHEN sm.movement_type IN ('sale', 'writeoff') THEN -sm.quantity
                ELSE 0
            END
        )
        FROM stock_movements sm
        WHERE sm.company_id = i.company_id
          AND sm.item_id = i.id
    ), 0)
"""


def _money(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def get_store(slug):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT ss.*, c.name AS company_name, c.phone AS company_phone,
                   c.address AS company_address, c.bin AS company_bin
            FROM storefront_settings ss
            JOIN companies c ON c.id = ss.company_id
            WHERE ss.slug = %s
              AND ss.enabled = TRUE
              AND c.is_active = TRUE
            LIMIT 1
        """, (slug,))
        return cur.fetchone()
    finally:
        cur.close()
        pool.putconn(conn)


def _cart_key(company_id):
    return f"store_cart_{company_id}"


def _cart_count(company_id):
    data = session.get(_cart_key(company_id), {})
    total = Decimal("0")
    for value in data.values():
        try:
            total += Decimal(str(value))
        except Exception:
            pass
    return total


def _ensure_customer(cur, company_id, name, phone, address=None):
    cur.execute("""
        SELECT id
        FROM clients
        WHERE company_id = %s
          AND phone = %s
          AND COALESCE(is_deleted, FALSE) = FALSE
        ORDER BY id DESC
        LIMIT 1
    """, (company_id, phone))
    row = cur.fetchone()

    if row:
        cur.execute("""
            UPDATE clients
            SET full_name = COALESCE(NULLIF(%s, ''), full_name),
                address = COALESCE(NULLIF(%s, ''), address)
            WHERE id = %s
        """, (name, address or "", row["id"]))
        return row["id"]

    cur.execute("""
        INSERT INTO clients (
            company_id, full_name, phone, address, status, category,
            created_at, is_deleted
        )
        VALUES (%s, %s, %s, %s, 'Новый', 'Онлайн', %s, FALSE)
        RETURNING id
    """, (company_id, name, phone, address or None, now_kz()))
    return cur.fetchone()["id"]


def _cart_payload(store):
    key = _cart_key(store["company_id"])
    data = session.get(key, {})
    ids = [int(x) for x in data.keys() if str(x).isdigit()]

    store_config = {
        "delivery_price": float(_money(store.get("delivery_price"))),
        "brand_color": store.get("brand_color") or "#6366f1",
    }

    if not ids:
        return {"items": [], "count": 0, "total": 0, **store_config}

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT
                i.id, i.name, i.retail_price, i.price, i.unit,
                {STOREFRONT_STOCK_SQL} AS quantity,
                (SELECT ii.image
                 FROM item_images ii
                 WHERE ii.item_id=i.id
                 ORDER BY ii.id LIMIT 1) AS image
            FROM items i
            WHERE i.company_id=%s AND i.id=ANY(%s)
        """, (store["company_id"], ids))
        rows = cur.fetchall()

        result = []
        total = Decimal("0")
        count = Decimal("0")

        for raw in rows:
            row = dict(raw)
            qty = Decimal(str(data.get(str(row["id"]), "1")))
            price = _money(row.get("retail_price") or row.get("price"))
            line_total = qty * price
            total += line_total
            count += qty

            result.append({
                "id": row["id"],
                "name": row["name"],
                "image": row.get("image"),
                "unit": row.get("unit") or "шт.",
                "quantity": float(qty),
                "price": float(price),
                "line_total": float(line_total),
                "stock": float(row["quantity"]) if row.get("quantity") is not None else None,
            })

        result.sort(key=lambda x: ids.index(x["id"]) if x["id"] in ids else 999999)

        return {
            "items": result,
            "count": float(count),
            "total": float(total),
            **store_config,
        }
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_bp.route("/<slug>")
def home(slug):
    store = get_store(slug)
    if not store:
        return "Витрина не найдена", 404

    category = (request.args.get("category") or "").strip()
    kind = (request.args.get("kind") or "all").strip().lower()
    if kind not in ("all", "products", "services"):
        kind = "all"

    conn = get_db()
    cur = conn.cursor()
    try:
        params = [store["company_id"]]
        filters = [
            "i.company_id=%s",
            "COALESCE(i.storefront_hidden,FALSE)=FALSE"
        ]

        cur.execute(f"""
            SELECT
                i.id, i.name, i.description, i.retail_price, i.price,
                i.discount_percent, i.category, i.unit,
                {STOREFRONT_STOCK_SQL} AS quantity,
                i.item_type, i.service_sale_mode, i.booking_enabled, i.booking_duration_minutes,
                (SELECT ii.image
                 FROM item_images ii
                 WHERE ii.item_id=i.id
                 ORDER BY ii.id LIMIT 1) AS image
            FROM items i
            WHERE {" AND ".join(filters)}
            ORDER BY
                CASE WHEN i.item_type='service' OR {STOREFRONT_STOCK_SQL}>0 THEN 0 ELSE 1 END,
                i.category NULLS LAST,
                i.name
        """, params)

        items = [dict(x) for x in cur.fetchall()]
        for item in items:
            item["category"] = (item.get("category") or "").strip()
            item["display_price"] = item.get("retail_price") or item.get("price") or 0

        products = [x for x in items if (x.get("item_type") or "product") != "service"]
        services = [x for x in items if x.get("item_type") == "service"]

        cur.execute("""
            SELECT
                BTRIM(category) AS category,
                BOOL_OR(COALESCE(item_type,'product') <> 'service') AS has_products,
                BOOL_OR(item_type='service') AS has_services
            FROM items
            WHERE company_id=%s
              AND COALESCE(storefront_hidden,FALSE)=FALSE
              AND category IS NOT NULL
              AND BTRIM(category)<>''
            GROUP BY BTRIM(category)
            ORDER BY BTRIM(category)
        """, (store["company_id"],))
        categories = [dict(x) for x in cur.fetchall()]

        cur.execute("""
            SELECT id, image_url, title, subtitle, button_text, button_url
            FROM storefront_banners
            WHERE company_id=%s AND is_active=TRUE
            ORDER BY sort_order, id
        """, (store["company_id"],))
        banners = cur.fetchall()

        return render_template(
            "storefront/home.html",
            store=store,
            products=products,
            services=services,
            categories=categories,
            selected_category=category,
            kind=kind,
            banners=banners,
            cart_count=_cart_count(store["company_id"]),
        )
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_bp.route("/<slug>/item/<int:item_id>/data")
def item_data(slug, item_id):
    store = get_store(slug)
    if not store:
        return jsonify({"ok": False, "error": "Витрина не найдена"}), 404

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT
                i.id, i.name, i.description, i.retail_price, i.price,
                i.discount_percent, i.category, i.unit,
                {STOREFRONT_STOCK_SQL} AS quantity,
                i.item_type, i.service_sale_mode, i.booking_enabled, i.booking_duration_minutes
            FROM items i
            WHERE i.id=%s
              AND i.company_id=%s
              AND COALESCE(i.storefront_hidden,FALSE)=FALSE
        """, (item_id, store["company_id"]))
        raw = cur.fetchone()

        if not raw:
            return jsonify({"ok": False, "error": "Позиция не найдена"}), 404

        item = dict(raw)
        price = _money(item.get("retail_price") or item.get("price"))

        cur.execute("""
            SELECT image
            FROM item_images
            WHERE item_id=%s
            ORDER BY id
        """, (item_id,))
        images = [x["image"] for x in cur.fetchall() if x.get("image")]

        cart = session.get(_cart_key(store["company_id"]), {})
        cart_qty = Decimal(str(cart.get(str(item_id), "0")))

        return jsonify({
            "ok": True,
            "item": {
                "id": item["id"],
                "name": item["name"],
                "description": item.get("description") or "",
                "category": item.get("category") or "",
                "price": float(price),
                "discount_percent": float(item.get("discount_percent") or 0),
                "unit": item.get("unit") or "шт.",
                "stock": float(item["quantity"]) if item.get("quantity") is not None else None,
                "item_type": item.get("item_type") or "product",
                "service_sale_mode": item.get("service_sale_mode") or "order",
                "booking_enabled": bool(item.get("booking_enabled", True)),
                "booking_duration_minutes": int(item.get("booking_duration_minutes") or 60),
                "images": images,
                "cart_quantity": float(cart_qty),
            }
        })
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_bp.route("/<slug>/item/<int:item_id>")
def item(slug, item_id):
    # Fallback для прямой ссылки / старых ссылок.
    # Основной UX теперь открывает карточку товара модалкой на главной.
    store = get_store(slug)
    if not store:
        return "Витрина не найдена", 404

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT i.*
            FROM items i
            WHERE i.id=%s AND i.company_id=%s
              AND COALESCE(i.storefront_hidden,FALSE)=FALSE
        """, (item_id, store["company_id"]))
        raw = cur.fetchone()

        if not raw:
            return "Позиция не найдена", 404

        item = dict(raw)
        item["display_price"] = item.get("retail_price") or item.get("price") or 0

        cur.execute("""
            SELECT image
            FROM item_images
            WHERE item_id=%s
            ORDER BY id
        """, (item_id,))
        images = [x["image"] for x in cur.fetchall() if x.get("image")]

        return render_template(
            "storefront/item.html",
            store=store,
            item=item,
            images=images,
            cart_count=_cart_count(store["company_id"]),
        )
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_bp.route("/<slug>/cart/data")
def cart_data(slug):
    store = get_store(slug)
    if not store:
        return jsonify({"ok": False, "error": "Витрина не найдена"}), 404

    payload = _cart_payload(store)
    payload["ok"] = True
    return jsonify(payload)


@storefront_bp.route("/<slug>/cart/add", methods=["POST"])
def cart_add(slug):
    store = get_store(slug)
    if not store:
        return jsonify({"ok": False, "error": "Витрина не найдена"}), 404

    raw_id = (request.form.get("item_id") or "").strip()
    if not raw_id.isdigit():
        return jsonify({"ok": False, "error": "Некорректная позиция"}), 400

    try:
        qty = Decimal(str(request.form.get("quantity") or "1"))
    except (InvalidOperation, ValueError):
        qty = Decimal("1")

    if qty <= 0:
        qty = Decimal("1")

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT
                i.id, i.item_type, i.service_sale_mode,
                {STOREFRONT_STOCK_SQL} AS quantity
            FROM items i
            WHERE i.id=%s
              AND i.company_id=%s
              AND COALESCE(i.storefront_hidden,FALSE)=FALSE
        """, (int(raw_id), store["company_id"]))
        item = cur.fetchone()

        if not item:
            return jsonify({"ok": False, "error": "Товар не найден"}), 404

        if item.get("item_type") == "service":
            mode = item.get("service_sale_mode") or "order"
            if mode == "booking":
                return jsonify({"ok": False, "error": "Для этой услуги используется онлайн-запись",
                                "booking_url": url_for("storefront.booking", slug=slug, item_id=int(raw_id))}), 409
            # Режим request оформляется как обычная заявка в online_orders.
            # Отличается только смыслом для менеджера: услуга требует уточнения деталей.

        # Остаток проверяем только для физических товаров.
        # Услуги с service_sale_mode='order' должны свободно добавляться в корзину,
        # даже если quantity у них равно 0.
        if (item.get("item_type") or "product") != "service" and item.get("quantity") is not None:
            stock = Decimal(str(item["quantity"]))
            if stock <= 0:
                return jsonify({"ok": False, "error": "Товара нет в наличии"}), 409

            current = Decimal(str(
                session.get(_cart_key(store["company_id"]), {}).get(raw_id, "0")
            ))
            if current + qty > stock:
                qty = max(Decimal("0"), stock - current)

            if qty <= 0:
                return jsonify({"ok": False, "error": "В корзине уже всё доступное количество"}), 409
    finally:
        cur.close()
        pool.putconn(conn)

    key = _cart_key(store["company_id"])
    cart = dict(session.get(key, {}))
    cart[raw_id] = str(Decimal(str(cart.get(raw_id, "0"))) + qty)
    session[key] = cart
    session.modified = True

    payload = _cart_payload(store)
    payload["ok"] = True
    return jsonify(payload)


@storefront_bp.route("/<slug>/cart/update", methods=["POST"])
def cart_update(slug):
    store = get_store(slug)
    if not store:
        return jsonify({"ok": False, "error": "Витрина не найдена"}), 404

    item_id = (request.form.get("item_id") or "").strip()
    if not item_id.isdigit():
        return jsonify({"ok": False, "error": "Некорректная позиция"}), 400

    key = _cart_key(store["company_id"])
    cart = dict(session.get(key, {}))

    if request.form.get("remove") == "1":
        cart.pop(item_id, None)
    else:
        try:
            qty = Decimal(str(request.form.get("quantity") or "1"))
        except (InvalidOperation, ValueError):
            qty = Decimal("1")

        if qty <= 0:
            cart.pop(item_id, None)
        else:
            conn = get_db()
            cur = conn.cursor()
            try:
                cur.execute(f"""
                    SELECT
                        i.item_type,
                        {STOREFRONT_STOCK_SQL} AS quantity
                    FROM items i
                    WHERE i.id=%s AND i.company_id=%s
                """, (int(item_id), store["company_id"]))
                row = cur.fetchone()

                if (
                    row
                    and (row.get("item_type") or "product") != "service"
                    and row.get("quantity") is not None
                ):
                    stock = Decimal(str(row["quantity"]))
                    qty = min(qty, stock)
            finally:
                cur.close()
                pool.putconn(conn)

            if qty <= 0:
                cart.pop(item_id, None)
            else:
                cart[item_id] = str(qty)

    session[key] = cart
    session.modified = True

    payload = _cart_payload(store)
    payload["ok"] = True
    return jsonify(payload)


@storefront_bp.route("/<slug>/cart")
def cart(slug):
    # Старый URL оставляем как fallback.
    store = get_store(slug)
    if not store:
        return "Витрина не найдена", 404

    payload = _cart_payload(store)

    items = []
    for row in payload["items"]:
        row = dict(row)
        row["cart_qty"] = row["quantity"]
        row["display_price"] = row["price"]
        items.append(row)

    return render_template(
        "storefront/cart.html",
        store=store,
        items=items,
        total=payload["total"],
    )



@storefront_bp.route("/<slug>/checkout-data")
def checkout_data(slug):
    store = get_store(slug)
    if not store:
        return jsonify({"ok": False, "error": "Витрина не найдена"}), 404

    payload = _cart_payload(store)
    payload["ok"] = True
    payload["store"] = {
        "pickup_enabled": bool(store.get("pickup_enabled")),
        "delivery_enabled": bool(store.get("delivery_enabled")),
        "delivery_price": float(_money(store.get("delivery_price"))),
        "min_order_amount": float(_money(store.get("min_order_amount"))),
    }
    return jsonify(payload)


@storefront_bp.route("/<slug>/checkout-ajax", methods=["POST"])
def checkout_ajax(slug):
    store = get_store(slug)
    if not store:
        return jsonify({"ok": False, "error": "Витрина не найдена"}), 404

    key = _cart_key(store["company_id"])
    data = session.get(key, {})

    if not data:
        return jsonify({"ok": False, "error": "Корзина пуста"}), 400

    name = (request.form.get("customer_name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    address = (request.form.get("address") or "").strip()
    method = (request.form.get("delivery_method") or "pickup").strip()
    comment = (request.form.get("comment") or "").strip()

    if len(name) < 2:
        return jsonify({"ok": False, "error": "Укажите имя"}), 400

    normalized_phone = re.sub(r"[^\d+]", "", phone)
    if len(re.sub(r"\D", "", normalized_phone)) < 10:
        return jsonify({"ok": False, "error": "Укажите корректный телефон"}), 400

    if method == "delivery":
        if not store.get("delivery_enabled"):
            return jsonify({"ok": False, "error": "Доставка недоступна"}), 400
        if len(address) < 5:
            return jsonify({"ok": False, "error": "Укажите адрес доставки"}), 400
    else:
        if not store.get("pickup_enabled"):
            return jsonify({"ok": False, "error": "Самовывоз недоступен"}), 400
        method = "pickup"

    ids = [int(x) for x in data if str(x).isdigit()]
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(f"""
            SELECT
                i.id, i.name, i.retail_price, i.price, i.unit, i.item_type,
                {STOREFRONT_STOCK_SQL} AS quantity
            FROM items i
            WHERE i.company_id=%s AND i.id=ANY(%s)
            FOR UPDATE OF i
        """, (store["company_id"], ids))
        rows = cur.fetchall()

        prepared = []
        subtotal = Decimal("0")

        for raw in rows:
            row = dict(raw)
            qty = Decimal(str(data.get(str(row["id"]), "1")))
            price = _money(row.get("retail_price") or row.get("price"))

            if (row.get("item_type") or "product") != "service" and row.get("quantity") is not None:
                stock = Decimal(str(row["quantity"]))
                if stock < qty:
                    return jsonify({
                        "ok": False,
                        "error": f"Недостаточно товара: {row['name']}"
                    }), 409

            line = qty * price
            subtotal += line
            prepared.append((row, qty, price, line))

        minimum = _money(store.get("min_order_amount"))
        if subtotal < minimum:
            return jsonify({
                "ok": False,
                "error": f"Минимальная сумма заказа — {minimum:.0f} ₸"
            }), 400

        delivery_price = Decimal("0")
        if method == "delivery":
            delivery_price = _money(store.get("delivery_price"))

        total = subtotal + delivery_price

        customer_id = _ensure_customer(
            cur,
            store["company_id"],
            name,
            phone,
            address if method == "delivery" else None,
        )

        cur.execute("""
            INSERT INTO online_orders (
                company_id, storefront_id, customer_id,
                customer_name, phone, address,
                delivery_method, comment, total_amount,
                payment_status, order_status, source, created_at
            )
            VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                'unpaid','new','storefront',%s
            )
            RETURNING id, created_at
        """, (
            store["company_id"],
            store["id"],
            customer_id,
            name,
            phone,
            address or None if method == "delivery" else None,
            method,
            comment or None,
            total,
            now_kz(),
        ))
        order = cur.fetchone()
        order_id = order["id"]

        for row, qty, price, line in prepared:
            cur.execute("""
                INSERT INTO online_order_items (
                    order_id, item_id, name, quantity, price, total
                )
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                order_id,
                row["id"],
                row["name"],
                qty,
                price,
                line,
            ))

        conn.commit()

        session.pop(key, None)
        session.modified = True

        return jsonify({
            "ok": True,
            "order": {
                "id": order_id,
                "customer_name": name,
                "phone": phone,
                "delivery_method": method,
                "address": address if method == "delivery" else "",
                "subtotal": float(subtotal),
                "delivery_price": float(delivery_price),
                "total": float(total),
            }
        })

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_bp.route("/<slug>/checkout", methods=["GET", "POST"])
def checkout(slug):
    store = get_store(slug)
    if not store:
        return "Витрина не найдена", 404

    key = _cart_key(store["company_id"])
    data = session.get(key, {})
    if not data:
        return redirect(url_for("storefront.home", slug=slug))

    if request.method == "GET":
        return render_template("storefront/checkout.html", store=store)

    name = (request.form.get("customer_name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    address = (request.form.get("address") or "").strip()
    method = (request.form.get("delivery_method") or "pickup").strip()
    comment = (request.form.get("comment") or "").strip()

    if not name or not phone:
        return render_template(
            "storefront/checkout.html",
            store=store,
            error="Укажите имя и телефон."
        )

    ids = [int(x) for x in data if str(x).isdigit()]
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(f"""
            SELECT
                i.id, i.name, i.retail_price, i.price, i.unit, i.item_type,
                {STOREFRONT_STOCK_SQL} AS quantity
            FROM items i
            WHERE i.company_id=%s AND i.id=ANY(%s)
        """, (store["company_id"], ids))
        rows = cur.fetchall()

        prepared = []
        subtotal = Decimal("0")

        for raw in rows:
            row = dict(raw)
            qty = Decimal(str(data.get(str(row["id"]), "1")))

            if (
                (row.get("item_type") or "product") != "service"
                and row.get("quantity") is not None
                and Decimal(str(row["quantity"])) < qty
            ):
                return render_template(
                    "storefront/checkout.html",
                    store=store,
                    error=f"Недостаточно товара: {row['name']}."
                )

            price = _money(row.get("retail_price") or row.get("price"))
            line = qty * price
            subtotal += line
            prepared.append((row, qty, price, line))

        delivery_price = Decimal("0")
        if method == "delivery" and store.get("delivery_enabled"):
            delivery_price = _money(store.get("delivery_price"))

        total = subtotal + delivery_price
        minimum = _money(store.get("min_order_amount"))

        if subtotal < minimum:
            return render_template(
                "storefront/checkout.html",
                store=store,
                error=f"Минимальная сумма заказа — {minimum:.0f} ₸."
            )

        customer_id = _ensure_customer(
            cur, store["company_id"], name, phone, address
        )

        cur.execute("""
            INSERT INTO online_orders (
                company_id, storefront_id, customer_id,
                customer_name, phone, address,
                delivery_method, comment, total_amount,
                payment_status, order_status, source, created_at
            )
            VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                'unpaid','new','storefront',%s
            )
            RETURNING id
        """, (
            store["company_id"],
            store["id"],
            customer_id,
            name,
            phone,
            address or None,
            method,
            comment or None,
            total,
            now_kz(),
        ))
        order_id = cur.fetchone()["id"]

        for row, qty, price, line in prepared:
            cur.execute("""
                INSERT INTO online_order_items (
                    order_id, item_id, name, quantity, price, total
                )
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                order_id,
                row["id"],
                row["name"],
                qty,
                price,
                line,
            ))

        conn.commit()
        session.pop(key, None)

        return redirect(
            url_for(
                "storefront.order_success",
                slug=slug,
                order_id=order_id
            )
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _slots_for(store, service, day):
    start = store.get("work_start")
    end = store.get("work_end")
    if not start or not end:
        return []

    duration = int(service.get("booking_duration_minutes") or 60)
    step = max(15, int(store.get("slot_interval_minutes") or 30))

    begin = datetime.combine(day, start)
    finish = datetime.combine(day, end)
    slots = []
    cursor = begin

    while cursor + timedelta(minutes=duration) <= finish:
        slots.append(cursor.time().strftime("%H:%M"))
        cursor += timedelta(minutes=step)

    return slots


@storefront_bp.route("/<slug>/booking/<int:item_id>", methods=["GET", "POST"])
def booking(slug, item_id):
    store = get_store(slug)
    if not store:
        return "Витрина не найдена", 404

    selected_date = (
        request.values.get("booking_date")
        or date.today().isoformat()
    ).strip()

    try:
        day = date.fromisoformat(selected_date)
    except ValueError:
        day = date.today()

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                id, name, description, retail_price, price, item_type,
                booking_duration_minutes, booking_enabled
            FROM items
            WHERE id=%s
              AND company_id=%s
              AND item_type='service'
              AND COALESCE(service_sale_mode,'order')='booking'
              AND COALESCE(storefront_hidden,FALSE)=FALSE
              AND COALESCE(booking_enabled,TRUE)=TRUE
        """, (item_id, store["company_id"]))
        service = cur.fetchone()

        if not service:
            return "Онлайн-запись для услуги недоступна", 404

        all_slots = _slots_for(store, service, day)

        cur.execute("""
            SELECT TO_CHAR(booking_time, 'HH24:MI') AS t
            FROM bookings
            WHERE company_id=%s
              AND item_id=%s
              AND booking_date=%s
              AND status NOT IN ('cancelled','rejected')
        """, (store["company_id"], item_id, day))
        busy = {x["t"] for x in cur.fetchall()}
        slots = [x for x in all_slots if x not in busy]

        if request.method == "GET":
            return render_template(
                "storefront/booking.html",
                store=store,
                service=service,
                selected_date=day.isoformat(),
                slots=slots,
            )

        name = (request.form.get("customer_name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        booking_time = (request.form.get("booking_time") or "").strip()
        comment = (request.form.get("comment") or "").strip()

        if not name or not phone or booking_time not in slots:
            return render_template(
                "storefront/booking.html",
                store=store,
                service=service,
                selected_date=day.isoformat(),
                slots=slots,
                error="Заполните контакты и выберите свободное время.",
            )

        customer_id = _ensure_customer(
            cur,
            store["company_id"],
            name,
            phone,
        )

        cur.execute("""
            INSERT INTO bookings (
                company_id, storefront_id, item_id, customer_id,
                customer_name, phone, booking_date, booking_time,
                duration_minutes, status, payment_status,
                comment, created_at
            )
            VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                'new','unpaid',%s,%s
            )
            RETURNING id
        """, (
            store["company_id"],
            store["id"],
            item_id,
            customer_id,
            name,
            phone,
            day,
            booking_time,
            int(service.get("booking_duration_minutes") or 60),
            comment or None,
            now_kz(),
        ))

        booking_id = cur.fetchone()["id"]
        conn.commit()

        return redirect(
            url_for(
                "storefront.booking_success",
                slug=slug,
                booking_id=booking_id
            )
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_bp.route("/<slug>/order/<int:order_id>/success")
def order_success(slug, order_id):
    store = get_store(slug)
    if not store:
        return "Витрина не найдена", 404

    return render_template(
        "storefront/success.html",
        store=store,
        title="Заказ принят",
        message=f"Заказ №{order_id} отправлен компании.",
    )


@storefront_bp.route("/<slug>/booking/<int:booking_id>/success")
def booking_success(slug, booking_id):
    store = get_store(slug)
    if not store:
        return "Витрина не найдена", 404

    return render_template(
        "storefront/success.html",
        store=store,
        title="Вы записаны",
        message=f"Запись №{booking_id} создана.",
    )
