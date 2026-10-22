"""Separate restaurant order journal and non-fiscal kitchen/guest tickets.

These orders DO NOT create sales, move stock or fiscalize receipts until the
existing /sales/pay pipeline commits the linked payment.
"""
import json
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, render_template, request, session
from models import get_db, pool
from utils.sale_amounts import normalize_sale_line
from utils.timezone import now_kz, now_kz_for_timestamp

food_orders_bp = Blueprint("food_orders", __name__)


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
            SELECT id, name, unit, gtin, ntin
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
        for field in ("id", "price", "qty", "line_total", "modifiers", "excise_stamp"):
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
            if status not in ("all", "open", "paid", "cancelled"):
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
                       sale_id, created_at, updated_at FROM food_orders
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
        cur.execute("SELECT * FROM food_orders WHERE id=%s AND company_id=%s",
                    (order_id, company_id))
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
                               company=company)
    finally:
        pool.putconn(conn)
