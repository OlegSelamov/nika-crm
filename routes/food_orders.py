"""Separate restaurant order journal and non-fiscal kitchen/guest tickets.

These orders DO NOT create sales, move stock or fiscalize receipts until the
existing /sales/pay pipeline commits the linked payment.
"""
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import Blueprint, jsonify, render_template, request, session
from models import get_db, pool
from utils.sale_amounts import normalize_sale_line
from utils.timezone import now_kz, now_kz_for_timestamp

food_orders_bp = Blueprint("food_orders", __name__)


def receipt_money(value):
    """Compact, readable tenge amounts, without dropping nonzero tiyins."""
    try:
        amount = Decimal(str(value if value is not None else 0))
        if not amount.is_finite():
            return "0"
        text = f"{amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
        return text.rstrip("0").rstrip(".").replace(",", " ").replace(".", "," )
    except (InvalidOperation, ValueError, TypeError):
        return "0"


def receipt_quantity(value):
    """Avoid tiny '1.0' or '1.00' labels on thermal checks."""
    try:
        quantity = Decimal(str(value if value is not None else 0))
        return format(quantity.normalize(), "f").replace(".", ",") if quantity.is_finite() else "0"
    except (InvalidOperation, ValueError, TypeError):
        return "0"


def _food_access(cur):
    company_id = session.get("company_id")
    if not company_id or not session.get("user_id"):
        return None
    cur.execute("SELECT business_mode FROM companies WHERE id=%s", (company_id,))
    row = cur.fetchone()
    return company_id if row and row["business_mode"] in ("foodservice", "universal") else None


def ensure_food_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS food_orders (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            created_by INTEGER,
            table_name TEXT NOT NULL DEFAULT '',
            guest_name TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            client_id INTEGER,
            status TEXT NOT NULL DEFAULT 'open',
            external_receipt_number TEXT,
            external_confirmed_at TIMESTAMP,
            cart JSONB NOT NULL DEFAULT '[]'::jsonb,
            total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
            sale_id INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_food_orders_company_created
        ON food_orders(company_id, created_at DESC, id DESC)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_food_orders_sale_id
        ON food_orders(sale_id) WHERE sale_id IS NOT NULL
    """)
    cur.execute("ALTER TABLE food_orders ADD COLUMN IF NOT EXISTS external_receipt_number TEXT")
    cur.execute("ALTER TABLE food_orders ADD COLUMN IF NOT EXISTS external_confirmed_at TIMESTAMP")
    # Legacy saved orders used timezone-aware datetime for a timezone-naive
    # column. PostgreSQL converted KZ +05:00 to UTC, moving the clock -5h.
    # Direct checkout orders were already saved with local naive wall time.
    # Repair legacy rows once and explicitly mark all subsequent writes.
    cur.execute("ALTER TABLE food_orders ADD COLUMN IF NOT EXISTS kz_clock_fixed BOOLEAN")
    cur.execute("""
        UPDATE food_orders AS fo
        SET created_at = CASE
            WHEN fo.sale_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM sales s
                WHERE s.id = fo.sale_id AND s.company_id = fo.company_id
                  AND ABS(EXTRACT(EPOCH FROM (fo.created_at - s.created_at))) < 120
            ) THEN fo.created_at
            ELSE fo.created_at + INTERVAL '5 hours'
        END,
        kz_clock_fixed = TRUE
        WHERE fo.kz_clock_fixed IS NULL
    """)


def normalize_excluded_ingredients(cur, company_id, item_id, item_type, raw):
    """Canonical recipe exclusions; never trust names or ingredient ids from the browser."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 50:
        raise ValueError("Некорректный список исключённых ингредиентов")
    if not raw:
        return []
    if item_type != "dish":
        raise ValueError("Убирать ингредиенты можно только из блюда")
    ids = []
    for value in raw:
        raw_id = value.get("id") if isinstance(value, dict) else value
        if isinstance(raw_id, bool):
            raise ValueError("Некорректный ингредиент для исключения")
        try:
            ingredient_id = int(raw_id)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Некорректный ингредиент для исключения")
        if ingredient_id <= 0 or ingredient_id in ids:
            raise ValueError("Повторяющийся или неверный ингредиент в исключениях")
        ids.append(ingredient_id)
    cur.execute("""
        SELECT r.ingredient_item_id AS id, i.name
        FROM item_recipes r
        JOIN items i ON i.id = r.ingredient_item_id AND i.company_id = r.company_id
        WHERE r.company_id = %s AND r.item_id = %s
          AND r.ingredient_item_id = ANY(%s)
    """, (company_id, item_id, ids))
    existing = {int(row["id"]): str(row["name"] or "Ингредиент") for row in cur.fetchall()}
    if len(existing) != len(ids):
        raise ValueError("Исключённый ингредиент отсутствует в техкарте блюда")
    return [{"id": ingredient_id, "name": existing[ingredient_id]} for ingredient_id in ids]


def _item_cart(cur, company_id, source):
    if not isinstance(source, list) or not 0 < len(source) <= 100:
        raise ValueError("Добавьте от 1 до 100 позиций в заказ")
    output = []
    total = Decimal("0")
    for raw in source:
        if not isinstance(raw, dict):
            raise ValueError("Некорректная позиция в заказе")
        try:
            item_id = int(raw.get("id"))
        except (TypeError, ValueError):
            raise ValueError("Некорректный товар в заказе")
        cur.execute("""
            SELECT id, name, unit, gtin, ntin, COALESCE(item_type, 'product') AS item_type
            FROM items
            WHERE company_id=%s AND id=%s
              AND COALESCE(item_type,'product') IN ('product','dish')
        """, (company_id, item_id))
        db_item = cur.fetchone()
        if not db_item:
            raise ValueError("Позиция заказа больше не доступна в каталоге")
        price, qty, line_total = normalize_sale_line(raw, db_item["unit"])
        if (not price.is_finite() or not qty.is_finite() or price < 0
                or qty <= 0 or qty > 1000 or price > 100000000):
            raise ValueError("Некорректная цена или количество")
        if line_total > Decimal("999999999"):
            raise ValueError("Сумма позиции слишком велика")
        modifiers = raw.get("modifiers") or []
        if not isinstance(modifiers, list) or len(modifiers) > 30:
            raise ValueError("Некорректные добавки к блюду")
        clean_modifiers = []
        for modifier in modifiers:
            if not isinstance(modifier, dict):
                raise ValueError("Некорректная добавка")
            clean_modifiers.append({
                "id": modifier.get("id"),
                "name": str(modifier.get("name") or "")[:120],
                "price_delta": float(modifier.get("price_delta") or 0)
            })
        removed_ingredients = normalize_excluded_ingredients(
            cur, company_id, item_id, db_item["item_type"], raw.get("excluded_ingredients")
        )
        row = {
            "id": item_id,
            "name": db_item["name"] or "Позиция",
            "unit": db_item["unit"] or "шт",
            "gtin": db_item["gtin"] or "",
            "ntin": db_item["ntin"] or "",
            "price": float(price),
            "qty": float(qty),
            "line_total": float(line_total),
            "modifiers": clean_modifiers,
            "excluded_ingredients": removed_ingredients,
        }
        # The fiscal flow must receive original marking codes when relevant.
        if raw.get("excise_stamp"):
            row["excise_stamp"] = str(raw["excise_stamp"])[:600]
        output.append(row)
        total += line_total
    if total > Decimal("999999999"):
        raise ValueError("Сумма заказа слишком велика")
    return output, total.quantize(Decimal("0.01"))


def _serialize(order):
    result = dict(order)
    for field in ("created_at", "updated_at"):
        if result.get(field):
            result[field] = result[field].isoformat()
    result["total_amount"] = float(result.get("total_amount") or 0)
    if result.get("created_at"):
        result["created_at_display"] = result["created_at"].replace("T", " ")[:16]
    cart = result.get("cart")
    if isinstance(cart, str):
        cart = json.loads(cart)
    result["cart"] = cart if isinstance(cart, list) else []
    return result


def verify_payment_order(cur, company_id, order_id, cart):
    """Lock and validate a saved restaurant order before any sale is created."""
    if not _food_access(cur) or not company_id:
        raise ValueError("Конфигурация общепита не включена")
    cur.execute("""
        SELECT id, cart, status, sale_id FROM food_orders
        WHERE id=%s AND company_id=%s FOR UPDATE
    """, (order_id, company_id))
    order = cur.fetchone()
    if not order:
        raise ValueError("Заказ общепита не найден")
    if order["status"] != "open" or order["sale_id"]:
        raise ValueError("Заказ уже оплачен или отменён. Не проводите оплату повторно")
    saved = order["cart"]
    if isinstance(saved, str):
        saved = json.loads(saved)
    given, _ = _item_cart(cur, company_id, cart)
    if len(saved) != len(given):
        raise ValueError("Заказ изменён: сохраните его перед оплатой")
    for left, right in zip(saved, given):
        for field in ("id", "price", "qty", "line_total", "modifiers", "excluded_ingredients", "excise_stamp"):
            if left.get(field) != right.get(field):
                raise ValueError("Заказ изменён: сохраните его перед оплатой")
    return order


@food_orders_bp.route("/api/food/orders", methods=["GET", "POST"])
def food_orders():
    conn = get_db()
    try:
        cur = conn.cursor()
        company_id = _food_access(cur)
        if company_id is None:
            return jsonify({"success": False, "message": "Доступно в конфигурациях Общепит и Универсальный"}), 403
        ensure_food_schema(cur)
        conn.commit()
        if request.method == "GET":
            try:
                page = max(1, int(request.args.get("page", "1")))
            except (ValueError, TypeError):
                page = 1
            status = request.args.get("status", "all")
            if status not in ("all", "open", "paid", "external_paid", "cancelled"):
                status = "all"
            query = (request.args.get("q") or "").strip()[:70]
            conditions = ["company_id=%s"]
            params = [company_id]
            if status != "all":
                conditions.append("status=%s")
                params.append(status)
            if query:
                conditions.append("(table_name ILIKE %s OR guest_name ILIKE %s OR CAST(id AS TEXT)=%s)")
                params.extend([f"%{query}%", f"%{query}%", query.lstrip("#")])
            where_sql = " AND ".join(conditions)
            cur.execute(f"""
                SELECT id, status, table_name, guest_name, total_amount,
                       sale_id, external_receipt_number, created_at, updated_at FROM food_orders
                WHERE {where_sql}
                ORDER BY id DESC LIMIT 21 OFFSET %s
            """, tuple(params + [(page - 1) * 20]))
            rows = cur.fetchall()
            return jsonify({
                "success": True,
                "orders": [_serialize(r) for r in rows[:20]],
                "page": page,
                "has_more": len(rows) > 20
            })

        data = request.get_json(silent=True) or {}
        try:
            order_id = int(data.get("id") or 0)
            table_name = str(data.get("table_name") or "").strip()[:80]
            guest_name = str(data.get("guest_name") or "").strip()[:100]
            note = str(data.get("note") or "").strip()[:500]
            cart, total = _item_cart(cur, company_id, data.get("cart"))
            client_id = int(data["client_id"]) if data.get("client_id") else None
            if client_id:
                cur.execute("""SELECT id FROM clients WHERE company_id=%s AND id=%s
                            AND COALESCE(is_deleted,FALSE)=FALSE""", (company_id, client_id))
                if not cur.fetchone():
                    raise ValueError("Указанный клиент не найден")
        except (ValueError, TypeError, InvalidOperation) as exc:
            conn.rollback()
            return jsonify({"success": False, "message": str(exc)}), 400
        payload = json.dumps(cart, ensure_ascii=False)
        if order_id:
            cur.execute("SELECT status FROM food_orders WHERE id=%s AND company_id=%s FOR UPDATE",
                        (order_id, company_id))
            existing = cur.fetchone()
            if not existing:
                conn.rollback()
                return jsonify({"success": False, "message": "Заказ не найден"}), 404
            if existing["status"] != "open":
                conn.rollback()
                return jsonify({"success": False, "message": "Оплаченный или отменённый заказ менять нельзя"}), 409
            cur.execute("""
                UPDATE food_orders SET table_name=%s, guest_name=%s, note=%s,
                    client_id=%s, cart=%s::jsonb, total_amount=%s, updated_at=%s
                WHERE id=%s AND company_id=%s RETURNING *
            """, (table_name, guest_name, note, client_id, payload, total, now_kz_for_timestamp(),
                  order_id, company_id))
        else:
            cur.execute("""
                INSERT INTO food_orders(company_id, created_by, table_name, guest_name, note,
                    client_id, cart, total_amount, created_at, updated_at, kz_clock_fixed)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,TRUE) RETURNING *
            """, (company_id, session["user_id"], table_name, guest_name, note,
                  client_id, payload, total, now_kz_for_timestamp(), now_kz_for_timestamp()))
        order = cur.fetchone()
        conn.commit()
        return jsonify({"success": True, "order": _serialize(order)})
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@food_orders_bp.route("/api/food/orders/<int:order_id>", methods=["GET", "POST"])
def food_order_detail(order_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        company_id = _food_access(cur)
        if company_id is None:
            return jsonify({"success": False, "message": "Доступно в конфигурациях Общепит и Универсальный"}), 403
        ensure_food_schema(cur)
        conn.commit()
        cur.execute("SELECT * FROM food_orders WHERE id=%s AND company_id=%s",
                    (order_id, company_id))
        order = cur.fetchone()
        if not order:
            return jsonify({"success": False, "message": "Заказ не найден"}), 404
        if request.method == "GET":
            return jsonify({"success": True, "order": _serialize(order)})
        action = (request.get_json(silent=True) or {}).get("action")
        if action != "cancel":
            return jsonify({"success": False, "message": "Неизвестное действие"}), 400
        cur.execute("""
            UPDATE food_orders SET status='cancelled', updated_at=%s
            WHERE id=%s AND company_id=%s AND status='open'
            RETURNING id
        """, (now_kz_for_timestamp(), order_id, company_id))
        if not cur.fetchone():
            conn.rollback()
            return jsonify({"success": False, "message": "Заказ уже закрыт"}), 409
        conn.commit()
        return jsonify({"success": True})
    finally:
        pool.putconn(conn)


@food_orders_bp.route("/api/food/orders/<int:order_id>/external-payment", methods=["POST"])
def food_order_external_payment(order_id):
    """Log manual external fiscal receipt confirmation, never fake a Nika sale."""
    conn = get_db()
    try:
        cur = conn.cursor()
        company_id = _food_access(cur)
        if company_id is None:
            return jsonify({"success": False, "message": "Нет доступа к заказам общепита"}), 403
        cur.execute("SELECT food_checkout_mode FROM companies WHERE id=%s", (company_id,))
        config = cur.fetchone()
        if not config or config["food_checkout_mode"] != "external":
            return jsonify({"success": False, "message": "Внешняя ККМ не выбрана в профиле"}), 403
        data = request.get_json(silent=True) or {}
        receipt = str(data.get("receipt_number") or "").strip()[:120]
        if not receipt:
            return jsonify({"success": False, "message": "Укажите номер фискального чека внешней ККМ"}), 400
        ensure_food_schema(cur)
        conn.commit()
        cur.execute("""
            UPDATE food_orders
               SET status='external_paid', external_receipt_number=%s,
                   external_confirmed_at=%s, updated_at=%s
             WHERE id=%s AND company_id=%s AND status='open' AND sale_id IS NULL
            RETURNING id, status, external_receipt_number
        """, (receipt, now_kz_for_timestamp(), now_kz_for_timestamp(), order_id, company_id))
        updated = cur.fetchone()
        if not updated:
            conn.rollback()
            return jsonify({"success": False, "message": "Заказ уже закрыт или не найден"}), 409
        conn.commit()
        return jsonify({"success": True, "order": dict(updated),
                        "message": "Номер внешнего чека сохранён; продажи и склад Nika не изменены"})
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@food_orders_bp.route("/food/orders/<int:order_id>/ticket/<kind>")
def food_order_ticket(order_id, kind):
    if kind not in ("kitchen", "precheck"):
        return "Документ не найден", 404
    conn = get_db()
    try:
        cur = conn.cursor()
        company_id = _food_access(cur)
        if company_id is None:
            return "Доступно в конфигурациях Общепит и Универсальный", 403
        ensure_food_schema(cur)
        conn.commit()  # Persist one-time repair before printing even on GET.
        cur.execute("""
            SELECT fo.*,
                   COALESCE(NULLIF(TRIM(u.full_name), ''), u.username, 'Кассир') AS cashier_name,
                   s.sale_type AS payment_method,
                   s.cash_received, s.change_amount,
                   s.cash_amount, s.card_amount, s.kaspi_amount
            FROM food_orders fo
            LEFT JOIN users u ON u.id=fo.created_by AND u.company_id=fo.company_id
            LEFT JOIN sales s ON s.id=fo.sale_id AND s.company_id=fo.company_id
            WHERE fo.id=%s AND fo.company_id=%s
        """, (order_id, company_id))
        order = cur.fetchone()
        if not order:
            return "Заказ не найден", 404
        cur.execute("""
            SELECT name, bin, address, phone,
                   COALESCE(to_jsonb(c)->>'legal_form', 'ip') AS legal_form
            FROM companies c WHERE id=%s
        """, (company_id,))
        company = cur.fetchone()
        return render_template("food_order_ticket.html",
                               kind=kind, order=_serialize(order),
                               company=company,
                               money=receipt_money, qty_text=receipt_quantity,
                               ticket_date=order["created_at"].strftime("%d.%m.%y %H:%M") if order.get("created_at") else "")
    finally:
        pool.putconn(conn)
