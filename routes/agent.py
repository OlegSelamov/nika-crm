from flask import Blueprint, request, jsonify
from models import get_db
from openai import OpenAI
import os
import json

agent_bp = Blueprint("agent", __name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔥 состояние диалога
dialog_state = {
    "pending_action": None,
    "data": {}
}

SYSTEM_PROMPT = """
Ты — голосовой ассистент CRM.

Преобразуй текст в JSON.

Формат:
{
  "action": "...",
  "name": "...",
  "client_name": "...",
  "item_name": "..."
}

Доступные действия:
- create_client
- create_sale_smart

ВАЖНО:
- Не выдумывай данные
- Если чего-то нет — не добавляй поле

Без текста. Только JSON.
"""

@agent_bp.route("/api/agent/command", methods=["POST"])
def agent_command():
    data = request.get_json() or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"reply": "Скажи команду"})

    # =========================
    # 🔥 ОБРАБОТКА ДИАЛОГА
    # =========================

    if dialog_state["pending_action"]:

        action = dialog_state["pending_action"]

        # 👉 ждём клиента
        if action == "await_client":
            dialog_state["data"]["client_name"] = text
            dialog_state["pending_action"] = "await_item"

            return jsonify({
                "reply": f"Что добавить клиенту {text}?"
            })

        # 👉 ждём товар
        if action == "await_item":
            dialog_state["data"]["item_name"] = text

            from routes.sales import smart_sale

            data_to_send = dialog_state["data"].copy()

            print("FINAL DATA:", data_to_send)  # 👈 отладка

            dialog_state["pending_action"] = None
            dialog_state["data"] = {}

            return smart_sale(data_to_send)

    # =========================
    # 🔥 GPT
    # =========================

    try:
        # 👉 собираем сообщения
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # 👉 добавляем контекст
        if dialog_state["data"]:
            messages.append({
                "role": "system",
                "content": f"Контекст: {json.dumps(dialog_state['data'], ensure_ascii=False)}"
            })

        # 👉 добавляем пользователя
        messages.append({
            "role": "user",
            "content": text
        })

        # 👉 вызываем GPT
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        reply = response.choices[0].message.content

        print("GPT RAW:", reply)

        try:
            command = json.loads(reply)
        except:
            return jsonify({
                "reply": "Я не поняла, попробуй сказать иначе"
            })

    except Exception as e:
        return jsonify({"reply": f"Ошибка: {str(e)}"})

    action = command.get("action")
    client_name = command.get("client_name")
    item_name = command.get("item_name")

    # =========================
    # 👉 СОЗДАНИЕ КЛИЕНТА
    # =========================

    if action == "create_client":
        conn = get_db()

        conn.execute("""
            INSERT INTO clients (full_name, phone, created_at)
            VALUES (?, ?, datetime('now'))
        """, (
            command.get("name"),
            command.get("phone", "")
        ))

        conn.commit()
        conn.close()

        return jsonify({
            "reply": f"Клиент {command.get('name')} создан"
        })

    # =========================
    # 👉 УМНАЯ ПРОДАЖА (с уточнениями)
    # =========================

    if action == "create_sale_smart":

        # ❗ нет клиента → спрашиваем
        if not client_name:
            dialog_state["pending_action"] = "await_client"
            dialog_state["data"] = {}

            return jsonify({
                "reply": "Кому добавить продажу?"
            })

        # ❗ нет товара → спрашиваем
        if not item_name:
            dialog_state["pending_action"] = "await_item"
            dialog_state["data"] = {
                "client_name": client_name
            }

            return jsonify({
                "reply": f"Что добавить клиенту {client_name}?"
            })

        # 👉 всё есть → создаём
        from routes.sales import smart_sale
        return smart_sale(command)

    return jsonify({
        "reply": "Не понял команду"
    })
