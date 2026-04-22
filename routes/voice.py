from flask import Blueprint, request, jsonify
import json
import os
from openai import OpenAI

voice_bp = Blueprint('voice', __name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

context = {
    "last_client": None
}

SYSTEM_PROMPT = """
Ты — голосовой ассистент CRM.

ВАЖНО:
- Никогда не изменяй имена
- Используй точные слова пользователя

Отвечай строго JSON:

{
  "action": "...",
  "name": "...",
  "client": "...",
  "amount": 0,
  "payment": "..."
}

Доступные действия:
- create_client
- create_sale
- find_client
- create_sale_smart (client_name, item_name)

Без текста. Только JSON.
"""

@voice_bp.route('/voice_command', methods=['POST'])
def voice_command():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Нет JSON"}), 400

    user_text = data.get('text')

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ]
        )

        reply = response.choices[0].message.content

        command = json.loads(reply)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(command)


# ======================
# ЛОГИКА
# ======================

context = {
    "last_client": None
}


def generate_id():
    return len(clients) + len(sales) + 1


def find_client_by_name(name):
    for c in clients:
        if c["name"].lower() == name.lower():
            return c
    return None


def execute_command(cmd):
    action = cmd.get("action")

    if action == "create_client":
        return create_client(cmd)

    elif action == "create_sale":
        return create_sale(cmd)

    elif action == "find_client":
        return find_client(cmd)

    return {"error": "Неизвестная команда"}

def find_client(cmd):
    name = cmd.get("name")

    client = find_client_by_name(name)

    if not client:
        return {"status": "not_found"}

    return {"status": "found", "client": client}


def find_client(cmd):
    name = cmd.get("name")

    client = find_client_by_name(name)

    if not client:
        return {"status": "not_found"}

    return {"status": "found", "client": client}
    
    