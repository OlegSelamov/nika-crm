import os
import requests

from flask import Blueprint, request, jsonify, session

from models import get_db, pool
from utils.timezone import now_kz


whatsapp_bp = Blueprint(
    "whatsapp",
    __name__,
    url_prefix="/whatsapp"
)


def release_db(conn):
    try:
        pool.putconn(conn)
    except Exception:
        pass


def get_company_integration(company_id):
    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM whatsapp_integrations
            WHERE company_id = %s
              AND enabled = TRUE
            LIMIT 1
        """, (company_id,))

        return cur.fetchone()

    finally:
        release_db(conn)


# =========================================================
# СОХРАНЕНИЕ GREEN-API
# =========================================================

@whatsapp_bp.route("/integration", methods=["POST"])
def save_integration():

    company_id = session.get("company_id")

    if not company_id:
        return jsonify({
            "ok": False,
            "error": "Компания не определена"
        }), 401

    data = request.get_json(silent=True) or request.form

    instance_id = str(data.get("instance_id", "")).strip()
    api_token = str(data.get("api_token", "")).strip()
    phone = str(data.get("phone", "")).strip()

    if not instance_id or not api_token:
        return jsonify({
            "ok": False,
            "error": "Укажите ID Instance и API Token"
        }), 400

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO whatsapp_integrations (
                company_id,
                provider,
                phone,
                instance_id,
                api_token,
                enabled,
                status,
                updated_at
            )
            VALUES (%s, 'green_api', %s, %s, %s, TRUE, 'connected', NOW())

            ON CONFLICT (company_id)
            DO UPDATE SET
                phone = EXCLUDED.phone,
                instance_id = EXCLUDED.instance_id,
                api_token = EXCLUDED.api_token,
                enabled = TRUE,
                updated_at = NOW()
        """, (
            company_id,
            phone,
            instance_id,
            api_token
        ))

        conn.commit()

        return jsonify({
            "ok": True
        })

    except Exception as e:
        conn.rollback()

        print("WHATSAPP SAVE ERROR:", e)

        return jsonify({
            "ok": False,
            "error": "Не удалось сохранить интеграцию"
        }), 500

    finally:
        release_db(conn)


# =========================================================
# ПРОВЕРКА СОСТОЯНИЯ GREEN-API
# =========================================================

@whatsapp_bp.route("/status")
def integration_status():

    company_id = session.get("company_id")

    if not company_id:
        return jsonify({
            "ok": False,
            "error": "Компания не определена"
        }), 401

    integration = get_company_integration(company_id)

    if not integration:
        return jsonify({
            "ok": True,
            "connected": False
        })

    instance_id = integration["instance_id"]
    api_token = integration["api_token"]

    url = (
        f"https://api.green-api.com/"
        f"waInstance{instance_id}/"
        f"getStateInstance/{api_token}"
    )

    try:
        response = requests.get(
            url,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        state = data.get("stateInstance")

        connected = state == "authorized"

        conn = get_db()

        try:
            cur = conn.cursor()

            cur.execute("""
                UPDATE whatsapp_integrations
                SET status = %s,
                    updated_at = NOW()
                WHERE company_id = %s
            """, (
                state or "unknown",
                company_id
            ))

            conn.commit()

        finally:
            release_db(conn)

        return jsonify({
            "ok": True,
            "connected": connected,
            "state": state,
            "phone": integration["phone"]
        })

    except Exception as e:

        print("GREEN API STATUS ERROR:", e)

        return jsonify({
            "ok": False,
            "connected": False,
            "error": "GREEN-API недоступен"
        }), 502


# =========================================================
# ОТПРАВКА СООБЩЕНИЯ
# =========================================================

@whatsapp_bp.route("/send", methods=["POST"])
def send_message():

    company_id = session.get("company_id")

    if not company_id:
        return jsonify({
            "ok": False,
            "error": "Компания не определена"
        }), 401

    data = request.get_json(silent=True) or request.form

    phone = str(data.get("phone", "")).strip()
    message = str(data.get("message", "")).strip()

    if not phone or not message:
        return jsonify({
            "ok": False,
            "error": "Укажите номер и сообщение"
        }), 400

    integration = get_company_integration(company_id)

    if not integration:
        return jsonify({
            "ok": False,
            "error": "WhatsApp не подключён"
        }), 400

    # Оставляем только цифры
    clean_phone = "".join(
        char for char in phone
        if char.isdigit()
    )

    # Казахстанский номер 8 777... -> 7 777...
    if clean_phone.startswith("8") and len(clean_phone) == 11:
        clean_phone = "7" + clean_phone[1:]

    chat_id = f"{clean_phone}@c.us"

    instance_id = integration["instance_id"]
    api_token = integration["api_token"]

    url = (
        f"https://api.green-api.com/"
        f"waInstance{instance_id}/"
        f"sendMessage/{api_token}"
    )

    try:

        response = requests.post(
            url,
            json={
                "chatId": chat_id,
                "message": message
            },
            timeout=20
        )

        response.raise_for_status()

        result = response.json()

        return jsonify({
            "ok": True,
            "message_id": result.get("idMessage")
        })

    except Exception as e:

        print("GREEN API SEND ERROR:", e)

        return jsonify({
            "ok": False,
            "error": "Не удалось отправить сообщение"
        }), 502



# =========================================================
# ЧАТЫ WHATSAPP ДЛЯ ВЕРХНЕЙ ШТОРКИ NIKA
# =========================================================

def _require_company():
    return bool(session.get("user_id") and session.get("company_id"))


def _safe_row_value(row, key, default=None):
    try:
        return row[key]
    except Exception:
        return default


@whatsapp_bp.route("/api/chats", methods=["GET"])
def whatsapp_chats_list():
    if not _require_company():
        return jsonify({"ok": False, "error": "Требуется авторизация"}), 401

    company_id = session.get("company_id")
    search = str(request.args.get("search", "")).strip()
    limit = min(max(request.args.get("limit", 100, type=int), 1), 200)

    conn = get_db()
    cur = conn.cursor()

    try:
        params = [company_id]
        where_search = ""

        if search:
            where_search = """
                AND (
                    COALESCE(wc.contact_name, '') ILIKE %s
                    OR COALESCE(wc.phone, '') ILIKE %s
                    OR COALESCE(wc.last_message, '') ILIKE %s
                )
            """
            needle = f"%{search}%"
            params.extend([needle, needle, needle])

        params.append(limit)

        cur.execute(f"""
            SELECT
                wc.id,
                wc.external_chat_id,
                wc.phone,
                wc.contact_name,
                wc.customer_id,
                wc.last_message,
                wc.last_message_at,
                COALESCE(wc.unread_count, 0) AS unread_count,
                COALESCE(c.full_name, wc.contact_name, wc.phone, 'Клиент') AS display_name
            FROM whatsapp_chats wc
            LEFT JOIN clients c
              ON c.id = wc.customer_id
             AND c.company_id = wc.company_id
            WHERE wc.company_id = %s
            {where_search}
            ORDER BY wc.last_message_at DESC NULLS LAST, wc.id DESC
            LIMIT %s
        """, tuple(params))

        rows = cur.fetchall()
        items = []
        total_unread = 0

        for row in rows:
            unread = int(_safe_row_value(row, "unread_count", 0) or 0)
            total_unread += unread
            last_at = _safe_row_value(row, "last_message_at")

            items.append({
                "id": _safe_row_value(row, "id"),
                "external_chat_id": _safe_row_value(row, "external_chat_id", ""),
                "phone": _safe_row_value(row, "phone", "") or "",
                "contact_name": _safe_row_value(row, "contact_name", "") or "",
                "display_name": _safe_row_value(row, "display_name", "Клиент") or "Клиент",
                "customer_id": _safe_row_value(row, "customer_id"),
                "last_message": _safe_row_value(row, "last_message", "") or "",
                "last_message_at_label": last_at.strftime("%d.%m.%Y %H:%M") if last_at else "",
                "last_message_at_short": last_at.strftime("%H:%M") if last_at else "",
                "unread_count": unread,
            })

        return jsonify({
            "ok": True,
            "items": items,
            "total_unread": total_unread,
        })

    except Exception as e:
        print("WHATSAPP CHATS LIST ERROR:", e)
        return jsonify({"ok": False, "error": "Не удалось загрузить WhatsApp-чаты"}), 500
    finally:
        try:
            cur.close()
        except Exception:
            pass
        release_db(conn)


@whatsapp_bp.route("/api/chats/<int:chat_id>/messages", methods=["GET"])
def whatsapp_chat_messages(chat_id):
    if not _require_company():
        return jsonify({"ok": False, "error": "Требуется авторизация"}), 401

    company_id = session.get("company_id")
    limit = min(max(request.args.get("limit", 150, type=int), 1), 300)

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, phone, contact_name, customer_id, external_chat_id
            FROM whatsapp_chats
            WHERE id = %s AND company_id = %s
            LIMIT 1
        """, (chat_id, company_id))
        chat = cur.fetchone()

        if not chat:
            return jsonify({"ok": False, "error": "Чат не найден"}), 404

        cur.execute("""
            SELECT *
            FROM (
                SELECT
                    id,
                    external_message_id,
                    direction,
                    message_type,
                    message_text,
                    sender_phone,
                    status,
                    is_ai,
                    created_at
                FROM whatsapp_messages
                WHERE company_id = %s
                  AND chat_id = %s
                ORDER BY id DESC
                LIMIT %s
            ) q
            ORDER BY q.id
        """, (company_id, chat_id, limit))

        items = []
        for row in cur.fetchall():
            created_at = _safe_row_value(row, "created_at")
            direction = _safe_row_value(row, "direction", "incoming") or "incoming"
            items.append({
                "id": _safe_row_value(row, "id"),
                "external_message_id": _safe_row_value(row, "external_message_id", "") or "",
                "direction": direction,
                "is_mine": direction == "outgoing",
                "message_type": _safe_row_value(row, "message_type", "textMessage") or "textMessage",
                "message": _safe_row_value(row, "message_text", "") or "",
                "sender_phone": _safe_row_value(row, "sender_phone", "") or "",
                "status": _safe_row_value(row, "status", "") or "",
                "is_ai": bool(_safe_row_value(row, "is_ai", False)),
                "created_at_label": created_at.strftime("%d.%m.%Y %H:%M") if created_at else "",
            })

        cur.execute("""
            UPDATE whatsapp_chats
            SET unread_count = 0,
                updated_at = NOW()
            WHERE id = %s AND company_id = %s
        """, (chat_id, company_id))
        conn.commit()

        return jsonify({
            "ok": True,
            "chat": {
                "id": _safe_row_value(chat, "id"),
                "phone": _safe_row_value(chat, "phone", "") or "",
                "contact_name": _safe_row_value(chat, "contact_name", "") or "",
                "customer_id": _safe_row_value(chat, "customer_id"),
                "external_chat_id": _safe_row_value(chat, "external_chat_id", "") or "",
            },
            "items": items,
        })

    except Exception as e:
        conn.rollback()
        print("WHATSAPP CHAT MESSAGES ERROR:", e)
        return jsonify({"ok": False, "error": "Не удалось загрузить переписку"}), 500
    finally:
        try:
            cur.close()
        except Exception:
            pass
        release_db(conn)


@whatsapp_bp.route("/api/chats/<int:chat_id>/messages", methods=["POST"])
def whatsapp_chat_send(chat_id):
    if not _require_company():
        return jsonify({"ok": False, "error": "Требуется авторизация"}), 401

    company_id = session.get("company_id")
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({"ok": False, "error": "Введите сообщение"}), 400

    if len(message) > 4000:
        return jsonify({"ok": False, "error": "Сообщение слишком длинное"}), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                wc.id,
                wc.external_chat_id,
                wc.phone,
                wc.integration_id,
                wi.instance_id,
                wi.api_token,
                wi.enabled,
                wi.phone AS integration_phone
            FROM whatsapp_chats wc
            JOIN whatsapp_integrations wi
              ON wi.id = wc.integration_id
             AND wi.company_id = wc.company_id
            WHERE wc.id = %s
              AND wc.company_id = %s
              AND wi.enabled = TRUE
            LIMIT 1
        """, (chat_id, company_id))
        chat = cur.fetchone()

        if not chat:
            return jsonify({"ok": False, "error": "Чат или интеграция не найдены"}), 404

        instance_id = _safe_row_value(chat, "instance_id")
        api_token = _safe_row_value(chat, "api_token")
        external_chat_id = _safe_row_value(chat, "external_chat_id")

        url = (
            f"https://api.green-api.com/"
            f"waInstance{instance_id}/"
            f"sendMessage/{api_token}"
        )

        response = requests.post(
            url,
            json={"chatId": external_chat_id, "message": message},
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()
        external_message_id = result.get("idMessage")

        cur.execute("""
            INSERT INTO whatsapp_messages (
                company_id,
                integration_id,
                chat_id,
                external_message_id,
                direction,
                message_type,
                message_text,
                sender_phone,
                status,
                is_ai,
                created_at
            )
            VALUES (
                %s, %s, %s, %s,
                'outgoing', 'textMessage', %s, %s,
                'sent', FALSE, NOW()
            )
            ON CONFLICT DO NOTHING
            RETURNING id
        """, (
            company_id,
            _safe_row_value(chat, "integration_id"),
            chat_id,
            external_message_id,
            message,
            _safe_row_value(chat, "integration_phone", "") or "",
        ))
        inserted = cur.fetchone()

        cur.execute("""
            UPDATE whatsapp_chats
            SET last_message = %s,
                last_message_at = NOW(),
                updated_at = NOW()
            WHERE id = %s AND company_id = %s
        """, (message, chat_id, company_id))

        conn.commit()

        return jsonify({
            "ok": True,
            "id": _safe_row_value(inserted, "id") if inserted else None,
            "external_message_id": external_message_id,
        })

    except requests.RequestException as e:
        conn.rollback()
        print("GREEN API CHAT SEND ERROR:", e)
        return jsonify({"ok": False, "error": "GREEN-API не отправил сообщение"}), 502
    except Exception as e:
        conn.rollback()
        print("WHATSAPP CHAT SEND ERROR:", e)
        return jsonify({"ok": False, "error": "Не удалось отправить сообщение"}), 500
    finally:
        try:
            cur.close()
        except Exception:
            pass
        release_db(conn)



# =========================================================
# КОНТЕКСТ КЛИЕНТА ДЛЯ WHATSAPP-ЧАТА
# =========================================================

@whatsapp_bp.route("/api/chats/<int:chat_id>/context", methods=["GET"])
def whatsapp_chat_context(chat_id):
    if not _require_company():
        return jsonify({"ok": False, "error": "Требуется авторизация"}), 401

    company_id = session.get("company_id")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT wc.id, wc.phone, wc.contact_name, wc.customer_id,
                   c.full_name, c.company_name, c.status, c.category,
                   c.payment, c.address, c.photo
            FROM whatsapp_chats wc
            LEFT JOIN clients c
              ON c.id = wc.customer_id AND c.company_id = wc.company_id
            WHERE wc.id = %s AND wc.company_id = %s
            LIMIT 1
        """, (chat_id, company_id))
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Чат не найден"}), 404

        customer_id = _safe_row_value(row, "customer_id")
        stats = {
            "sales_count": 0,
            "total_revenue": 0,
            "average_check": 0,
            "debt": 0,
            "last_sale_at": "",
            "last_sale_total": 0,
        }

        if customer_id:
            cur.execute("""
                SELECT
                    COUNT(*) AS sales_count,
                    COALESCE(SUM(total_amount) FILTER (WHERE status = 'Оплачено'), 0) AS total_revenue,
                    COALESCE(AVG(total_amount) FILTER (WHERE status = 'Оплачено'), 0) AS average_check,
                    COALESCE(SUM(GREATEST(COALESCE(total_amount,0)-COALESCE(paid_amount,0),0)),0) AS debt
                FROM sales
                WHERE company_id = %s AND client_id = %s
            """, (company_id, customer_id))
            aggregate = cur.fetchone() or {}
            stats.update({
                "sales_count": int(_safe_row_value(aggregate, "sales_count", 0) or 0),
                "total_revenue": float(_safe_row_value(aggregate, "total_revenue", 0) or 0),
                "average_check": float(_safe_row_value(aggregate, "average_check", 0) or 0),
                "debt": float(_safe_row_value(aggregate, "debt", 0) or 0),
            })
            cur.execute("""
                SELECT total_amount, created_at
                FROM sales
                WHERE company_id = %s AND client_id = %s
                ORDER BY id DESC
                LIMIT 1
            """, (company_id, customer_id))
            last_sale = cur.fetchone()
            if last_sale:
                created = _safe_row_value(last_sale, "created_at")
                stats["last_sale_at"] = created.strftime("%d.%m.%Y %H:%M") if created else ""
                stats["last_sale_total"] = float(_safe_row_value(last_sale, "total_amount", 0) or 0)

        return jsonify({
            "ok": True,
            "client": {
                "id": customer_id,
                "full_name": _safe_row_value(row, "full_name") or _safe_row_value(row, "contact_name") or _safe_row_value(row, "phone") or "Клиент WhatsApp",
                "company_name": _safe_row_value(row, "company_name") or "",
                "phone": _safe_row_value(row, "phone") or "",
                "status": _safe_row_value(row, "status") or "",
                "category": _safe_row_value(row, "category") or "",
                "payment": _safe_row_value(row, "payment") or "",
                "address": _safe_row_value(row, "address") or "",
                "photo": _safe_row_value(row, "photo") or "",
            },
            "stats": stats,
        })
    except Exception as e:
        print("WHATSAPP CONTEXT ERROR:", e)
        return jsonify({"ok": False, "error": "Не удалось загрузить карточку клиента"}), 500
    finally:
        try: cur.close()
        except Exception: pass
        release_db(conn)


@whatsapp_bp.route("/api/chats/<int:chat_id>/create-client", methods=["POST"])
def whatsapp_create_client(chat_id):
    if not _require_company():
        return jsonify({"ok": False, "error": "Требуется авторизация"}), 401

    company_id = session.get("company_id")
    data = request.get_json(silent=True) or {}
    full_name = str(data.get("full_name", "")).strip()
    if not full_name:
        return jsonify({"ok": False, "error": "Укажите имя клиента"}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, phone, customer_id
            FROM whatsapp_chats
            WHERE id = %s AND company_id = %s
            LIMIT 1
        """, (chat_id, company_id))
        chat = cur.fetchone()
        if not chat:
            return jsonify({"ok": False, "error": "Чат не найден"}), 404
        if _safe_row_value(chat, "customer_id"):
            return jsonify({"ok": True, "customer_id": _safe_row_value(chat, "customer_id")})

        cur.execute("""
            INSERT INTO clients (
                full_name, phone, status, payment, created_at,
                company_id, is_deleted, comment
            )
            VALUES (%s, %s, 'Новый', 'Не оплачено', %s, %s, FALSE, %s)
            RETURNING id
        """, (
            full_name,
            _safe_row_value(chat, "phone") or "",
            now_kz(),
            company_id,
            "Создан из WhatsApp-чата Nika Business",
        ))
        customer_id = cur.fetchone()["id"]
        cur.execute("""
            UPDATE whatsapp_chats
            SET customer_id = %s, contact_name = %s, updated_at = NOW()
            WHERE id = %s AND company_id = %s
        """, (customer_id, full_name, chat_id, company_id))
        conn.commit()
        return jsonify({"ok": True, "customer_id": customer_id})
    except Exception as e:
        conn.rollback()
        print("WHATSAPP CREATE CLIENT ERROR:", e)
        return jsonify({"ok": False, "error": "Не удалось создать клиента"}), 500
    finally:
        try: cur.close()
        except Exception: pass
        release_db(conn)

# =========================================================
# WEBHOOK GREEN-API
# =========================================================

@whatsapp_bp.route("/webhook", methods=["POST"])
def green_api_webhook():

    payload = request.get_json(silent=True)

    if not payload:
        return jsonify({"ok": True})

    try:

        instance_id = str(
            payload.get("instanceData", {}).get("idInstance", "")
        )

        if not instance_id:
            return jsonify({"ok": True})

        conn = get_db()

        try:
            cur = conn.cursor()

            cur.execute("""
                SELECT *
                FROM whatsapp_integrations
                WHERE instance_id = %s
                  AND enabled = TRUE
                LIMIT 1
            """, (instance_id,))

            integration = cur.fetchone()

            if not integration:
                return jsonify({"ok": True})

            company_id = integration["company_id"]

            webhook_type = payload.get("typeWebhook")

            # Обновляем статусы исходящих сообщений.
            if webhook_type in ("outgoingMessageStatus", "outgoingAPIMessageReceived"):
                message_id = payload.get("idMessage")
                status = payload.get("status") or payload.get("statusMessage") or "sent"
                if message_id:
                    cur.execute("""
                        UPDATE whatsapp_messages
                        SET status = %s
                        WHERE integration_id = %s
                          AND external_message_id = %s
                    """, (status, integration["id"], message_id))
                    conn.commit()
                return jsonify({"ok": True})

            if webhook_type != "incomingMessageReceived":
                return jsonify({"ok": True})

            sender_data = payload.get("senderData") or {}

            external_chat_id = sender_data.get("chatId")
            sender_phone = sender_data.get("sender")
            contact_name = sender_data.get("senderName")

            message_data = payload.get("messageData") or {}

            message_type = message_data.get(
                "typeMessage",
                "unknown"
            )

            text = ""

            if message_type == "textMessage":

                text = (
                    message_data
                    .get("textMessageData", {})
                    .get("textMessage", "")
                )

            elif message_type == "extendedTextMessage":

                text = (
                    message_data
                    .get("extendedTextMessageData", {})
                    .get("text", "")
                )

            external_message_id = payload.get("idMessage")

            # -------------------------------------------------
            # Пытаемся найти клиента по номеру
            # -------------------------------------------------

            customer_id = None

            clean_sender = "".join(
                char for char in str(sender_phone or "")
                if char.isdigit()
            )

            if clean_sender:

                cur.execute("""
                    SELECT id
                    FROM clients
                    WHERE company_id = %s
                      AND regexp_replace(
                            COALESCE(phone, ''),
                            '[^0-9]',
                            '',
                            'g'
                          ) = %s
                    LIMIT 1
                """, (
                    company_id,
                    clean_sender
                ))

                customer = cur.fetchone()

                if customer:
                    customer_id = customer["id"]

            # -------------------------------------------------
            # ЧАТ
            # -------------------------------------------------

            cur.execute("""
                INSERT INTO whatsapp_chats (
                    company_id,
                    integration_id,
                    external_chat_id,
                    phone,
                    contact_name,
                    customer_id,
                    last_message,
                    last_message_at,
                    unread_count,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, NOW(), 1, NOW()
                )

                ON CONFLICT (
                    integration_id,
                    external_chat_id
                )

                DO UPDATE SET
                    phone = EXCLUDED.phone,
                    contact_name = EXCLUDED.contact_name,

                    customer_id = COALESCE(
                        whatsapp_chats.customer_id,
                        EXCLUDED.customer_id
                    ),

                    last_message = EXCLUDED.last_message,
                    last_message_at = NOW(),

                    unread_count =
                        whatsapp_chats.unread_count + 1,

                    updated_at = NOW()

                RETURNING id
            """, (
                company_id,
                integration["id"],
                external_chat_id,
                sender_phone,
                contact_name,
                customer_id,
                text,
            ))

            chat = cur.fetchone()
            chat_db_id = chat["id"]

            # -------------------------------------------------
            # СООБЩЕНИЕ
            # -------------------------------------------------

            cur.execute("""
                INSERT INTO whatsapp_messages (
                    company_id,
                    integration_id,
                    chat_id,
                    external_message_id,
                    direction,
                    message_type,
                    message_text,
                    sender_phone,
                    status,
                    is_ai
                )
                VALUES (
                    %s, %s, %s, %s,
                    'incoming',
                    %s, %s, %s,
                    'received',
                    FALSE
                )

                ON CONFLICT DO NOTHING
            """, (
                company_id,
                integration["id"],
                chat_db_id,
                external_message_id,
                message_type,
                text,
                sender_phone
            ))

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            release_db(conn)

        return jsonify({"ok": True})

    except Exception as e:

        print("GREEN API WEBHOOK ERROR:", e)

        # Webhook лучше подтвердить даже при внутренней ошибке,
        # чтобы провайдер не зациклил одно событие.
        return jsonify({"ok": True})