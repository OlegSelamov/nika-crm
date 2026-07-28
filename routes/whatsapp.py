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

            # Пока обрабатываем только входящие сообщения
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