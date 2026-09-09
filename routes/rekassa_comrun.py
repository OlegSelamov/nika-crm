from flask import jsonify, request, session

from models import get_db, pool
from services.fiscal_service import fiscalize_sale
from utils.timezone import now_kz


def _mark_fiscal_error(conn, sale_id, result):
    """Keep legacy reKassa status storage until neutral sale columns are migrated."""
    message = result.get("message") or "Ошибка фискализации"
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE sales SET rekassa_status=%s WHERE id=%s",
            (("ERROR: " + str(message))[:500], sale_id),
        )
    finally:
        cur.close()


def pay_sale_comrun():
    """Compatibility entry point: Sales is provider-neutral despite old name."""
    from routes.sales import process_sale

    data = request.get_json(silent=True) or {}
    company_id = session.get("company_id")
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Требуется войти в систему"}), 401
    if not company_id:
        return jsonify({"success": False, "error": "Активная организация не выбрана"}), 403

    client_id = data.get("client_id")
    cart = data.get("cart") or []
    if not client_id:
        return jsonify({"success": False, "error": "Клиент не выбран"}), 400
    if not isinstance(cart, list) or not cart:
        return jsonify({"success": False, "error": "Корзина пуста"}), 400

    payment_method = str(data.get("payment_method") or "cash").lower()
    if payment_method not in {"cash", "card", "kaspi"}:
        payment_method = "cash"

    total = sum(
        float(item.get("price") or 0) * float(item.get("qty") or 1)
        for item in cart
        if isinstance(item, dict)
    )
    if total <= 0:
        return jsonify({"success": False, "error": "Сумма продажи должна быть больше нуля"}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT COALESCE(MAX(sale_number),0)+1 AS next_number FROM sales WHERE company_id=%s",
                (company_id,),
            )
            sale_number = cur.fetchone()["next_number"]
            cash = total if payment_method == "cash" else 0
            card = total if payment_method == "card" else 0
            kaspi = total if payment_method == "kaspi" else 0
            cur.execute("""
                INSERT INTO sales (
                    client_id, company_id, user_id, sale_number, total_amount, paid_amount,
                    status, created_at, sale_type, cash_amount, card_amount, kaspi_amount,
                    kaspi_transaction_id, kaspi_method
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                client_id, company_id, user_id, sale_number, total, total, "Оплачено", now_kz(),
                payment_method, cash, card, kaspi,
                data.get("kaspi_transaction_id"), data.get("kaspi_method"),
            ))
            sale_id = cur.fetchone()["id"]

            for item in cart:
                item_id = item.get("id")
                cur.execute(
                    "SELECT unit, COALESCE(item_type,'product') AS item_type FROM items WHERE id=%s",
                    (item_id,),
                )
                db_item = cur.fetchone()
                unit = db_item["unit"] if db_item and db_item.get("unit") else "шт"
                item_type = (db_item["item_type"] if db_item else "product") or "product"
                price = float(item.get("price") or 0)
                qty = float(item.get("qty") or 1)
                cur.execute("""
                    INSERT INTO sale_items (
                        sale_id,item_id,name,price,quantity,total,unit,gtin,ntin,excise_stamp,item_type
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    sale_id, item_id, item.get("name") or f"Товар #{item_id}",
                    price, qty, price * qty, unit,
                    item.get("gtin"), item.get("ntin"), item.get("excise_stamp"), item_type,
                ))
        finally:
            cur.close()

        # Core sale/stock operations are committed regardless of fiscal provider.
        process_sale(conn, sale_id)
        fiscal = fiscalize_sale(conn, sale_id, company_id)
        if not fiscal.get("skipped") and not fiscal.get("fiscalized"):
            _mark_fiscal_error(conn, sale_id, fiscal)

        conn.commit()

        response = {
            "success": True,
            "sale_id": sale_id,
            "fiscalized": bool(fiscal.get("fiscalized")),
            "fiscalization_skipped": bool(fiscal.get("skipped")),
            "fiscal": {
                "configured": not bool(fiscal.get("skipped")),
                "provider": fiscal.get("provider"),
                "provider_name": fiscal.get("provider_name"),
                "code": fiscal.get("code"),
                "message": fiscal.get("message"),
                "action_url": fiscal.get("action_url"),
                "ticket_id": fiscal.get("ticket_id"),
                "ticket_number": fiscal.get("ticket_number"),
                "shift_number": fiscal.get("shift_number"),
            },
        }

        # Backwards-compatible response for existing clients while they migrate
        # from `rekassa` to the neutral `fiscal` object.
        response["rekassa"] = {
            "configured": response["fiscal"]["configured"],
            "status": "OK" if response["fiscalized"] else ("SKIPPED" if response["fiscalization_skipped"] else "ERROR"),
            "message": response["fiscal"]["message"],
            "code": response["fiscal"]["code"],
            "comrun_payment_url": response["fiscal"]["action_url"],
            "ticket_id": response["fiscal"]["ticket_id"],
            "ticket_number": response["fiscal"]["ticket_number"],
            "shift_number": response["fiscal"]["shift_number"],
        }
        return jsonify(response)
    except Exception as exc:
        conn.rollback()
        print("SALE FISCAL LAYER ERROR:", repr(exc))
        return jsonify({"success": False, "error": "Не удалось сохранить продажу"}), 500
    finally:
        pool.putconn(conn)


def fiscalize_sale_comrun(sale_id):
    """Compatibility endpoint delegates to provider-neutral fiscal API logic."""
    from routes.fiscal import fiscalize_existing_sale
    return fiscalize_existing_sale(sale_id)
