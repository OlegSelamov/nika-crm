from flask import jsonify, request, session

from models import get_db, pool
from services.fiscal_service import fiscalize_sale, provider_context
from utils.timezone import now_kz
from routes.rekassa import rekassa_bp


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


def _fiscal_context():
    company_id = session.get("company_id")
    conn = get_db()
    try:
        return provider_context(conn, company_id)
    finally:
        pool.putconn(conn)


def _fiscal_status_response():
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Требуется войти в систему"}), 401
    if not session.get("company_id"):
        return jsonify({"success": False, "error": "Активная организация не выбрана"}), 403

    context = _fiscal_context()
    if not context["configured"]:
        return jsonify({
            "success": True,
            "configured": False,
            "provider": None,
            "provider_name": None,
            "capabilities": context["capabilities"],
            "shift_open": False,
            "shift_number": None,
        })

    if context["provider"] == "rekassa":
        from routes.rekassa import _load_company_rekassa, _register_state, _safe_shift_state
        rekassa_context, error = _load_company_rekassa()
        if error:
            return error
        state, error = _register_state(rekassa_context)
        if error:
            return error
        data = _safe_shift_state(state, rekassa_context)
        data.update({
            "success": True,
            "configured": True,
            "provider": context["provider"],
            "provider_name": context["provider_name"],
            "capabilities": context["capabilities"],
        })
        return jsonify(data)

    return jsonify({
        "success": True,
        "configured": True,
        "provider": context["provider"],
        "provider_name": context["provider_name"],
        "capabilities": context["capabilities"],
        "shift_open": False,
        "shift_number": None,
    })


@rekassa_bp.route("/api/fiscal/status", methods=["GET"])
def fiscal_status_compat():
    return _fiscal_status_response()


@rekassa_bp.route("/api/fiscal/sales/<int:sale_id>/fiscalize", methods=["POST"])
def fiscalize_sale_neutral(sale_id):
    return fiscalize_sale_comrun(sale_id)


@rekassa_bp.before_request
def fiscal_legacy_route_adapter():
    """Keep legacy reKassa URLs working while Sales moves to /api/fiscal."""
    path = request.path
    if not path.startswith("/api/rekassa/"):
        return None

    # Settings, diagnostics and login are provider-specific and must remain
    # untouched. Only Sales fiscal controls are normalized here.
    mapped = {
        "/api/rekassa/shift/status": "status",
        "/api/rekassa/reports/x": "x",
        "/api/rekassa/shifts/close": "close",
        "/api/rekassa/shifts": "shifts",
    }
    action = mapped.get(path)
    report_match = None
    if path.startswith("/api/rekassa/shifts/") and path.endswith("/report"):
        parts = path.strip("/").split("/")
        if len(parts) >= 5:
            try:
                report_match = int(parts[-2])
            except ValueError:
                report_match = None

    if not action and report_match is None:
        return None

    context = _fiscal_context()
    if not context["configured"]:
        if action == "status":
            return _fiscal_status_response()
        if action == "shifts":
            return jsonify({
                "success": True,
                "configured": False,
                "provider": None,
                "provider_name": None,
                "history": [],
                "has_more": False,
            })
        return jsonify({
            "success": False,
            "configured": False,
            "code": "FISCAL_NOT_CONFIGURED",
            "error": "Фискальная касса не подключена",
        }), 409

    # reKassa remains one normal adapter and can continue through its original
    # endpoint implementation. Other providers are handled here as their
    # adapters are connected.
    if context["provider"] == "rekassa":
        return None

    if action == "status":
        return _fiscal_status_response()
    if action == "shifts":
        return jsonify({
            "success": True,
            "configured": True,
            "provider": context["provider"],
            "provider_name": context["provider_name"],
            "history": [],
            "has_more": False,
        })

    capability = {
        "x": "x_report",
        "close": "z_report",
    }.get(action, "z_report")
    if not context["capabilities"].get(capability):
        return jsonify({
            "success": False,
            "configured": True,
            "provider": context["provider"],
            "provider_name": context["provider_name"],
            "code": "FISCAL_CAPABILITY_UNSUPPORTED",
            "error": f"{context['provider_name']} не поддерживает эту операцию через Nika",
        }), 409

    return jsonify({
        "success": False,
        "configured": True,
        "provider": context["provider"],
        "provider_name": context["provider_name"],
        "code": "FISCAL_ADAPTER_NOT_READY",
        "error": f"Адаптер {context['provider_name']} ещё не подключён к фискальному слою Nika",
    }), 501


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
    """Compatibility endpoint using the active fiscal provider."""
    company_id = session.get("company_id")
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Требуется войти в систему"}), 401
    if not company_id:
        return jsonify({"success": False, "error": "Активная организация не выбрана"}), 403

    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id, rekassa_ticket_id FROM sales WHERE id=%s AND company_id=%s FOR UPDATE",
                (sale_id, company_id),
            )
            sale = cur.fetchone()
        finally:
            cur.close()

        if not sale:
            conn.rollback()
            return jsonify({"success": False, "error": "Продажа не найдена"}), 404
        if sale.get("rekassa_ticket_id"):
            conn.commit()
            return jsonify({
                "success": True,
                "fiscalized": True,
                "message": "Чек уже фискализирован",
                "ticket_id": sale.get("rekassa_ticket_id"),
            })

        result = fiscalize_sale(conn, sale_id, company_id)
        if result.get("skipped"):
            conn.commit()
            return jsonify({
                "success": True,
                "fiscalized": False,
                "skipped": True,
                "configured": False,
                "provider": None,
            })

        if not result.get("fiscalized"):
            _mark_fiscal_error(conn, sale_id, result)
            conn.commit()
            return jsonify({
                "success": False,
                "fiscalized": False,
                "configured": True,
                "provider": result.get("provider"),
                "provider_name": result.get("provider_name"),
                "code": result.get("code"),
                "error": result.get("message"),
                "action_url": result.get("action_url"),
                "comrun_payment_url": result.get("action_url"),
                "details": result.get("details"),
                "sale_id": sale_id,
            }), 409 if result.get("code") == "FISCAL_OFD_PAYMENT_REQUIRED" else 422

        return jsonify({
            "success": True,
            "fiscalized": True,
            "configured": True,
            "provider": result.get("provider"),
            "provider_name": result.get("provider_name"),
            "ticket_id": result.get("ticket_id"),
            "ticket_number": result.get("ticket_number"),
            "shift_number": result.get("shift_number"),
            "sale_id": sale_id,
        })
    except Exception as exc:
        conn.rollback()
        print("FISCAL RETRY ERROR:", repr(exc))
        return jsonify({"success": False, "fiscalized": False, "error": "Не удалось повторить фискализацию"}), 500
    finally:
        pool.putconn(conn)
