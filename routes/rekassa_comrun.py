import json
from decimal import Decimal, InvalidOperation
from flask import current_app, jsonify, request, session

from models import get_db, pool
from services.fiscal_service import fiscalize_sale, provider_context
from utils.timezone import now_kz, now_kz_for_timestamp
from utils.sale_amounts import normalize_sale_line
from utils.offline_operations import lock_and_load_offline_operation, save_offline_operation, offline_operation_age_seconds
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


def _sale_movement_totals(cur, company_id, item_ids):
    if not item_ids:
        return {}
    cur.execute("""
        SELECT item_id, COALESCE(SUM(quantity), 0) AS qty
        FROM stock_movements
        WHERE company_id = %s
          AND movement_type = 'sale'
          AND item_id = ANY(%s)
        GROUP BY item_id
    """, (company_id, list(item_ids)))
    return {int(row["item_id"]): float(row["qty"] or 0) for row in cur.fetchall()}


def _ensure_sale_stock_movements(conn, sale_id, company_id, normalized_cart, before_totals):
    """Guarantee that a completed product sale always changes the stock ledger."""
    expected = {}
    for normalized in normalized_cart:
        if normalized["item_type"] != "product":
            continue
        item_id = int(normalized["item_id"])
        bucket = expected.setdefault(item_id, {"qty": 0.0, "total": 0.0, "price": 0.0})
        qty = float(normalized["qty"] or 0)
        bucket["qty"] += qty
        bucket["total"] += float(normalized["total"] or 0)
        if qty > 0:
            bucket["price"] = float(normalized["price"] or 0)

    if not expected:
        return

    cur = conn.cursor()
    try:
        after_totals = _sale_movement_totals(cur, company_id, expected.keys())
        for item_id, values in expected.items():
            before = float(before_totals.get(item_id, 0) or 0)
            after = float(after_totals.get(item_id, 0) or 0)
            moved = after - before
            missing = values["qty"] - moved
            if missing <= 0.000001:
                continue

            unit_price = values["price"]
            movement_total = missing * unit_price
            cur.execute("""
                INSERT INTO stock_movements (
                    company_id,
                    item_id,
                    movement_type,
                    quantity,
                    price,
                    total,
                    comment,
                    created_at
                ) VALUES (%s,%s,'sale',%s,%s,%s,%s,%s)
            """, (
                company_id,
                item_id,
                missing,
                unit_price,
                movement_total,
                f"Автосинхронизация продажи #{sale_id}",
                now_kz(),
            ))
    finally:
        cur.close()


def pay_sale_comrun():
    """Compatibility entry point: Sales is provider-neutral despite old name."""
    from routes.sales import process_sale, _resolve_sale_client

    data = request.get_json(silent=True) or {}
    company_id = session.get("company_id")
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Требуется войти в систему"}), 401
    if not company_id:
        return jsonify({"success": False, "error": "Активная организация не выбрана"}), 403

    client_id = data.get("client_id")
    operation_id = str(data.get("operation_id") or "").strip()
    cart = data.get("cart") or []
    if not isinstance(cart, list) or not cart:
        return jsonify({"success": False, "error": "Корзина пуста"}), 400

    payment_method = str(data.get("payment_method") or "cash").lower()
    if payment_method not in {"cash", "card", "kaspi"}:
        payment_method = "cash"

    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            # app.py maps /sales/pay to THIS function, not routes.sales.pay_sale.
            # Persist and check operation_id so network retries never create
            # a second sale, stock movement or paid receipt.
            if operation_id:
                existing = lock_and_load_offline_operation(
                    conn, cur, company_id, operation_id
                )
                if existing:
                    if existing.get("operation_type") != "sale":
                        conn.rollback()
                        return jsonify({
                            "success": False,
                            "error": "Этот operation_id уже использован другой операцией",
                        }), 409
                    previous_result = existing.get("result")
                    if isinstance(previous_result, dict):
                        conn.commit()
                        return jsonify({**previous_result, "duplicate": True})

                    existing_sale_id = existing.get("entity_id")
                    if existing_sale_id:
                        cur.execute("""
                            SELECT id, rekassa_ticket_id, rekassa_ticket_number,
                                   rekassa_shift_number, rekassa_status
                            FROM sales WHERE id=%s AND company_id=%s
                        """, (existing_sale_id, company_id))
                        sale = cur.fetchone()
                        if not sale:
                            conn.rollback()
                            return jsonify({
                                "success": False,
                                "error": "Операция зарегистрирована, но продажа не найдена",
                            }), 409
                        fiscalized = bool(sale.get("rekassa_ticket_id"))
                        processing = (
                            not fiscalized
                            and offline_operation_age_seconds(existing) < 45
                        )
                        conn.commit()
                        return jsonify({
                            "success": True,
                            "duplicate": True,
                            "pending": processing,
                            "sale_id": existing_sale_id,
                            "fiscalized": fiscalized,
                            "rekassa_required": True,
                            "rekassa": {
                                "status": "OK" if fiscalized else "PENDING",
                                "message": "Продажа уже сохранена. Проверьте фискализацию чека отдельно.",
                                "ticket_id": sale.get("rekassa_ticket_id"),
                                "ticket_number": sale.get("rekassa_ticket_number"),
                                "shift_number": sale.get("rekassa_shift_number"),
                            },
                        })

            # For the anonymous default client the phone may have no id.
            # Resolve it for this company instead of rejecting the queued sale.
            try:
                client_id = _resolve_sale_client(cur, company_id, client_id)
            except ValueError as exc:
                conn.rollback()
                return jsonify({"success": False, "error": str(exc)}), 400

            food_order_id = data.get("food_order_id") or None
            food_mode = data.get("food_mode") is True or food_order_id is not None
            if food_mode:
                from routes.food_orders import _food_access, ensure_food_schema, verify_payment_order
                if _food_access(cur) != company_id:
                    conn.rollback()
                    return jsonify({"success": False, "error": "Режим общепита не включён"}), 403
                ensure_food_schema(cur)
                if food_order_id is not None:
                    try:
                        food_order_id = int(food_order_id)
                        verify_payment_order(cur, company_id, food_order_id, cart)
                    except (TypeError, ValueError) as exc:
                        conn.rollback()
                        return jsonify({"success": False, "error": str(exc)}), 409

            normalized_cart = []
            for item in cart:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id")
                cur.execute(
                    "SELECT unit, COALESCE(item_type,'product') AS item_type FROM items WHERE id=%s AND company_id=%s",
                    (item_id, company_id),
                )
                db_item = cur.fetchone()
                if not db_item:
                    continue
                unit = db_item["unit"] if db_item.get("unit") else "шт"
                raw_item_type = str(db_item.get("item_type") or "product").strip().lower()
                # Dish sales must retain their type so process_sale consumes recipe
                # ingredients, not the dish item itself.
                item_type = raw_item_type if raw_item_type in ("service", "dish") else "product"
                price, qty, line_total = normalize_sale_line(item, unit)
                normalized_cart.append({
                    "source": item,
                    "item_id": item_id,
                    "unit": unit,
                    "item_type": item_type,
                    "price": price,
                    "qty": qty,
                    "total": line_total,
                })

            if not normalized_cart:
                return jsonify({"success": False, "error": "В корзине нет доступных товаров"}), 400

            total = sum((item["total"] for item in normalized_cart), start=0)
            if total <= 0:
                return jsonify({"success": False, "error": "Сумма продажи должна быть больше нуля"}), 400

            product_ids = {
                int(item["item_id"])
                for item in normalized_cart
                if item["item_type"] == "product"
            }
            movement_before = _sale_movement_totals(cur, company_id, product_ids)

            cur.execute(
                "SELECT COALESCE(MAX(sale_number),0)+1 AS next_number FROM sales WHERE company_id=%s",
                (company_id,),
            )
            sale_number = cur.fetchone()["next_number"]
            cash = total if payment_method == "cash" else 0
            card = total if payment_method == "card" else 0
            kaspi = total if payment_method == "kaspi" else 0
            cash_received = Decimal("0")
            change_amount = Decimal("0")
            if payment_method == "cash":
                try:
                    cash_received = Decimal(str(data.get("cash_received") or total))
                except (ValueError, InvalidOperation, TypeError):
                    cash_received = total
                if not cash_received.is_finite() or cash_received < total:
                    cash_received = total
                change_amount = cash_received - total
            cur.execute("""
                INSERT INTO sales (
                    client_id, company_id, user_id, sale_number, total_amount, paid_amount,
                    status, created_at, sale_type, cash_amount, card_amount, kaspi_amount,
                    kaspi_transaction_id, kaspi_method, is_processed,
                    cash_received, change_amount
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,%s,%s)
                RETURNING id
            """, (
                client_id, company_id, user_id, sale_number, total, total, "Оплачено", now_kz(),
                payment_method, cash, card, kaspi,
                data.get("kaspi_transaction_id"), data.get("kaspi_method"),
                cash_received, change_amount,
            ))
            sale_id = cur.fetchone()["id"]

            for normalized in normalized_cart:
                item = normalized["source"]
                item_id = normalized["item_id"]
                cur.execute("""
                    INSERT INTO sale_items (
                        sale_id,item_id,name,price,quantity,total,unit,gtin,ntin,excise_stamp,item_type,modifiers
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    sale_id, item_id, item.get("name") or f"Товар #{item_id}",
                    normalized["price"], normalized["qty"], normalized["total"], normalized["unit"],
                    item.get("gtin"), item.get("ntin"), item.get("excise_stamp"), normalized["item_type"],
                    json.dumps(item.get("modifiers") or [], ensure_ascii=False),
                ))
        finally:
            cur.close()

        process_sale(conn, sale_id)
        _ensure_sale_stock_movements(conn, sale_id, company_id, normalized_cart, movement_before)

        # Keep the food-order journal consistent with the paid sale and recipe
        # deductions. This is one database transaction; no second sale is made.
        if food_mode:
            from routes.food_orders import _item_cart
            food_cur = conn.cursor()
            try:
                if food_order_id is None:
                    food_cart, food_total = _item_cart(food_cur, company_id, cart)
                    food_cur.execute("""
                        INSERT INTO food_orders
                            (company_id, created_by, table_name, guest_name, note,
                             client_id, status, cart, total_amount, sale_id,
                             created_at, updated_at, kz_clock_fixed)
                        VALUES (%s,%s,%s,%s,%s,%s,'paid',%s::jsonb,%s,%s,%s,%s,TRUE)
                    """, (
                        company_id, user_id,
                        str(data.get("food_table_name") or "")[:80],
                        str(data.get("food_guest_name") or "")[:100],
                        str(data.get("food_note") or "")[:500],
                        client_id, json.dumps(food_cart, ensure_ascii=False),
                        food_total, sale_id, now_kz_for_timestamp(), now_kz_for_timestamp(),
                    ))
                else:
                    food_cur.execute("""
                        UPDATE food_orders SET status='paid', sale_id=%s,
                            updated_at=%s, kz_clock_fixed=TRUE
                        WHERE id=%s AND company_id=%s AND status='open' AND sale_id IS NULL
                        RETURNING id
                    """, (sale_id, now_kz_for_timestamp(), food_order_id, company_id))
                    if not food_cur.fetchone():
                        raise ValueError("Заказ уже оплачен или отменён")
            finally:
                food_cur.close()

        # Atomic with sale and stock: survive crash during fiscalization.
        if operation_id:
            op_cur = conn.cursor()
            try:
                save_offline_operation(
                    op_cur, company_id=company_id,
                    operation_id=operation_id, operation_type="sale",
                    entity_id=sale_id,
                )
            finally:
                op_cur.close()

        # Сначала фиксируем продажу, склад и прибыль в Nika. Внешняя
        # фискализация не должна откатывать уже принятую оплату.
        conn.commit()

        try:
            fiscal = fiscalize_sale(conn, sale_id, company_id)
            if not isinstance(fiscal, dict):
                fiscal = {
                    "success": False,
                    "fiscalized": False,
                    "skipped": False,
                    "provider": "rekassa",
                    "provider_name": "reKassa",
                    "code": "FISCAL_INVALID_RESPONSE",
                    "message": "reKassa вернула ответ неизвестного формата",
                }
        except Exception as exc:
            # Продажа уже сохранена. Ошибку внешней кассы показываем отдельно
            # и оставляем возможность повторной фискализации по sale_id.
            conn.rollback()
            print("SALE FISCALIZATION ERROR:", repr(exc))
            fiscal = {
                "success": False,
                "fiscalized": False,
                "skipped": False,
                "provider": "rekassa",
                "provider_name": "reKassa",
                "code": "FISCAL_PROVIDER_ERROR",
                "message": f"Не удалось фискализировать чек: {exc}",
            }

        if not fiscal.get("skipped") and not fiscal.get("fiscalized"):
            try:
                _mark_fiscal_error(conn, sale_id, fiscal)
                conn.commit()
            except Exception as mark_exc:
                conn.rollback()
                print("SALE FISCAL STATUS SAVE ERROR:", repr(mark_exc))

        response = {
            "success": True,
            "sale_id": sale_id,
            "fiscalized": bool(fiscal.get("fiscalized")),
            "fiscalization_skipped": bool(fiscal.get("skipped")),
            "rekassa_required": not bool(fiscal.get("skipped")),
            "fiscal": {
                "configured": not bool(fiscal.get("skipped")),
                "provider": fiscal.get("provider"),
                "provider_name": fiscal.get("provider_name"),
                "code": fiscal.get("code"),
                "message": fiscal.get("message"),
                "http_status": fiscal.get("http_status"),
                "details": fiscal.get("details"),
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
        if operation_id:
            op_cur = conn.cursor()
            try:
                save_offline_operation(
                    op_cur, company_id=company_id,
                    operation_id=operation_id, operation_type="sale",
                    entity_id=sale_id, result=response,
                )
                conn.commit()
            finally:
                op_cur.close()
        return jsonify(response)
    except Exception as exc:
        conn.rollback()
        current_app.logger.exception("SALE FISCAL LAYER ERROR")
        # Detailed diagnostics are only available on the isolated TEST server.
        # Production clients always receive the generic error without SQL data.
        message = "Не удалось сохранить продажу"
        if current_app.config.get("APP_MODE") == "test":
            message += f": {type(exc).__name__}: {str(exc)[:240]}"
        return jsonify({"success": False, "error": message}), 500
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
        # A manually verified fiscal receipt must never be sent again.
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT manual_fiscalized_at, manual_fiscal_receipt_url
                FROM sales WHERE id=%s AND company_id=%s
            """, (sale_id, company_id))
            manual = cur.fetchone() or {}
        finally:
            cur.close()
        if manual.get("manual_fiscalized_at"):
            conn.commit()
            return jsonify({
                "success": True,
                "fiscalized": True,
                "already_fiscalized_manually": True,
                "message": "Чек уже пробит вручную в reKassa; повторная фискализация запрещена",
                "receipt_url": manual.get("manual_fiscal_receipt_url"),
            })

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
