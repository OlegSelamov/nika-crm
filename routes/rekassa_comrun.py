import json
import re

from flask import Blueprint, jsonify, request, session

from models import get_db, pool
from utils.timezone import now_kz


rekassa_comrun_bp = Blueprint("rekassa_comrun", __name__)
OFD_CODE = "REKASSA_OFD_PAYMENT_REQUIRED"
OFD_MESSAGE = "Требуется оплатить ОФД COMRUN"


def _payment_url():
    from routes.rekassa import REKASSA_URL
    return "https://ofd-test.rekassa.kz" if "test" in str(REKASSA_URL or "").lower() else "https://ofd.rekassa.kz"


def _integration(conn, company_id):
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM integrations WHERE company_id=%s ORDER BY id DESC LIMIT 1", (company_id,))
        row = cur.fetchone()
        data = dict(row) if row else {}
    finally:
        cur.close()
    configured = bool(data.get("rekassa_enabled") and data.get("rekassa_number") and data.get("rekassa_password") and data.get("rekassa_crs_id"))
    return data, configured


def _ofd_required(result):
    if not isinstance(result, dict):
        return False
    text = json.dumps(result, ensure_ascii=False, default=str).lower()
    text = re.sub(r"[\s_-]+", " ", text)
    return (
        "cash register ofd payment required" in text
        or "ofd payment required" in text
        or ("оплат" in text and ("ofd" in text or "офд" in text))
    )


def _error_meta(result):
    if _ofd_required(result):
        return {"code": OFD_CODE, "message": OFD_MESSAGE, "comrun_payment_url": _payment_url()}
    return {
        "code": "REKASSA_FISCALIZATION_ERROR",
        "message": result.get("message") or result.get("error") or "reKassa отклонила чек",
        "comrun_payment_url": None,
    }


def _mark_error(conn, sale_id, message):
    cur = conn.cursor()
    try:
        cur.execute("UPDATE sales SET rekassa_status=%s WHERE id=%s", (("ERROR: " + str(message))[:500], sale_id))
    finally:
        cur.close()


@rekassa_comrun_bp.route("/sales/pay", methods=["POST"])
def pay_sale_comrun():
    from routes.sales import process_sale
    from routes.rekassa import rekassa_sell

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

    total = sum(float(i.get("price") or 0) * float(i.get("qty") or 1) for i in cart if isinstance(i, dict))
    if total <= 0:
        return jsonify({"success": False, "error": "Сумма продажи должна быть больше нуля"}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT COALESCE(MAX(sale_number),0)+1 AS next_number FROM sales WHERE company_id=%s", (company_id,))
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
                payment_method, cash, card, kaspi, data.get("kaspi_transaction_id"), data.get("kaspi_method")
            ))
            sale_id = cur.fetchone()["id"]

            for item in cart:
                item_id = item.get("id")
                cur.execute("SELECT unit, COALESCE(item_type,'product') AS item_type FROM items WHERE id=%s", (item_id,))
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
                    sale_id, item_id, item.get("name") or f"Товар #{item_id}", price, qty, price*qty,
                    unit, item.get("gtin"), item.get("ntin"), item.get("excise_stamp"), item_type
                ))
        finally:
            cur.close()

        process_sale(conn, sale_id)
        _, configured = _integration(conn, company_id)
        result = {"status": "SKIPPED"}
        meta = None
        fiscalized = False

        if configured:
            result = rekassa_sell(conn, sale_id)
            fiscalized = result.get("status") == "OK"
            if not fiscalized:
                meta = _error_meta(result)
                _mark_error(conn, sale_id, meta["message"])

        conn.commit()
        return jsonify({
            "success": True,
            "sale_id": sale_id,
            "fiscalized": fiscalized,
            "fiscalization_skipped": not configured,
            "rekassa": {
                "configured": configured,
                "status": result.get("status"),
                "message": meta["message"] if meta else result.get("message") or result.get("error"),
                "code": meta["code"] if meta else None,
                "comrun_payment_url": meta["comrun_payment_url"] if meta else None,
                "ticket_id": result.get("id"),
                "ticket_number": result.get("ticketNumber"),
                "shift_number": result.get("shiftNumber"),
            }
        })
    except Exception as exc:
        conn.rollback()
        print("COMRUN SALE ERROR:", repr(exc))
        return jsonify({"success": False, "error": "Не удалось сохранить продажу"}), 500
    finally:
        pool.putconn(conn)


@rekassa_comrun_bp.route("/api/rekassa/sales/<int:sale_id>/fiscalize", methods=["POST"])
def fiscalize_sale_comrun(sale_id):
    from routes.rekassa import rekassa_sell

    company_id = session.get("company_id")
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Требуется войти в систему"}), 401
    if not company_id:
        return jsonify({"success": False, "error": "Активная организация не выбрана"}), 403

    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT id,rekassa_ticket_id FROM sales WHERE id=%s AND company_id=%s FOR UPDATE", (sale_id, company_id))
            sale = cur.fetchone()
        finally:
            cur.close()

        if not sale:
            conn.rollback()
            return jsonify({"success": False, "error": "Продажа не найдена"}), 404
        if sale.get("rekassa_ticket_id"):
            conn.commit()
            return jsonify({"success": True, "fiscalized": True, "message": "Чек уже фискализирован", "ticket_id": sale.get("rekassa_ticket_id")})

        _, configured = _integration(conn, company_id)
        if not configured:
            conn.commit()
            return jsonify({
                "success": False, "fiscalized": False, "configured": False,
                "code": "REKASSA_NOT_CONFIGURED",
                "error": "reKassa не подключена. Продажа сохранена в Nika без фискализации."
            }), 409

        result = rekassa_sell(conn, sale_id)
        if result.get("status") != "OK":
            meta = _error_meta(result)
            _mark_error(conn, sale_id, meta["message"])
            conn.commit()
            return jsonify({
                "success": False, "fiscalized": False, "configured": True,
                "code": meta["code"], "error": meta["message"],
                "comrun_payment_url": meta["comrun_payment_url"],
                "details": result.get("details"), "http_status": result.get("http_status"),
                "sale_id": sale_id
            }), 409 if meta["code"] == OFD_CODE else 422

        return jsonify({
            "success": True, "fiscalized": True, "configured": True,
            "message": "Чек фискализирован", "ticket_id": result.get("id"),
            "ticket_number": result.get("ticketNumber"), "shift_number": result.get("shiftNumber"),
            "sale_id": sale_id
        })
    except Exception as exc:
        conn.rollback()
        print("COMRUN RETRY ERROR:", repr(exc))
        return jsonify({"success": False, "fiscalized": False, "error": "Не удалось повторить фискализацию"}), 500
    finally:
        pool.putconn(conn)
