from flask import jsonify, request, session

from models import get_db, pool
from routes.expenses import upsert_expense_from_source, _sync_expense_to_accounting
from routes.stock import is_product
from routes.suppliers import (
    _supplier_for_company,
    ensure_supplier_schema,
    suppliers_bp,
)
from utils.stock_pricing import apply_income_pricing, as_bool
from utils.timezone import now_kz


@suppliers_bp.route("/api/mobile/stock/income/supplier", methods=["POST"])
def mobile_stock_income_with_supplier():
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    data = request.get_json(silent=True) or {}

    try:
        item_id = int(data.get("item_id"))
        supplier_id = int(data.get("supplier_id"))
        quantity = float(data.get("quantity", 0))
        price = float(data.get("price", 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Некорректные данные прихода"}), 400

    if quantity <= 0:
        return jsonify({"success": False, "error": "Количество должно быть больше нуля"}), 400
    if price < 0:
        return jsonify({"success": False, "error": "Закупочная цена не может быть отрицательной"}), 400

    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()

        if not is_product(cur, item_id, company_id):
            return jsonify({"success": False, "error": "Приход доступен только для товаров"}), 400

        supplier = _supplier_for_company(cur, supplier_id, company_id)
        if not supplier:
            return jsonify({"success": False, "error": "Поставщик не найден"}), 404

        pricing = apply_income_pricing(
            cur,
            company_id=company_id,
            item_id=item_id,
            quantity=quantity,
            price=price,
            update_retail=as_bool(data.get("update_retail")),
        )

        comment = str(data.get("comment") or "").strip() or None
        total = quantity * price
        movement_datetime = now_kz().replace(tzinfo=None)

        cur.execute("""
            INSERT INTO stock_movements (
                company_id, item_id, movement_type, quantity, price,
                total, comment, supplier_id, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            company_id,
            item_id,
            "income",
            quantity,
            price,
            total,
            comment,
            supplier["id"],
            movement_datetime,
        ))
        movement_id = cur.fetchone()["id"]

        expense_id = upsert_expense_from_source(
            cur,
            company_id=company_id,
            source_type="stock_income",
            source_id=movement_id,
            category="Закупки",
            description=f"Закуп товара: {pricing['item_name']} · {supplier['name']}",
            amount=total,
            expense_date=movement_datetime.date(),
            payment_method="Другое",
            comment=comment or f"Поставщик: {supplier['name']}",
            user_id=session.get("user_id"),
        )
        _sync_expense_to_accounting(cur, expense_id, company_id)

        conn.commit()
        return jsonify({
            "success": True,
            "movement_id": movement_id,
            "supplier": {
                "id": supplier["id"],
                "name": supplier["name"],
            },
            "pricing": pricing,
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
