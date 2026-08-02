import json
import os
import re
import threading
import time
import uuid
from html import unescape
from datetime import timedelta
from decimal import Decimal

from flask import Blueprint, Response, current_app, jsonify, request, session
from openai import APIConnectionError, APIStatusError, OpenAI

from models import get_db, pool
from routes.ai_actions import (
    ACTION_NAMES,
    ActionError,
    PermissionDenied,
    execute_action,
    prepare_action,
)
from utils.timezone import now_kz


ai_bp = Blueprint("ai", __name__)

AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
AI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
AI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "marin")
AI_MAX_HISTORY = 16
AI_MAX_TOOL_ROUNDS = 3
AI_REQUEST_ATTEMPTS = 3
AI_TABLES_LOCK = threading.Lock()
_ai_tables_ready = False


AI_INSTRUCTIONS = """
Ты Nika AI — встроенный бизнес-ассистент Nika Business.
Отвечай на языке пользователя, по умолчанию на русском. Общайся естественно, тепло и уверенно, как внимательный живой помощник, а не как справочник или робот.
Пиши кратко, понятно и по делу. Используй короткие предложения, естественные запятые и точки: ответ должен хорошо звучать вслух без спешки. Не перегружай одну фразу множеством цифр и фактов.
Отвечай только обычным текстом: не используй Markdown, звёздочки, решётки, обратные кавычки, ссылки в скобках и служебные символы. Для перечислений используй короткие строки без маркеров.
Для любых актуальных данных о продажах, прибыли, товарах, остатках, клиентах, задачах, расходах, бухгалтерии, пользователях или организациях обязательно используй доступные функции.
Не выдумывай цифры и не утверждай, что действие выполнено, если функция его не выполняла.
Когда пользователь просит создать, изменить, удалить, оплатить, списать или провести запись, обязательно вызови prepare_action. В action укажи точное действие, а в data_json передай JSON-объект с реальными полями. Не говори, что действие выполнено: prepare_action только готовит подтверждение.
Если для действия нужен id, сначала найди запись функцией поиска. Не угадывай id.
Одно подтверждение относится только к одному подготовленному действию. Права определяет сервер. Никогда не обещай обход прав, не проси пароль существующей учётной записи и не повторяй пароль в ответе. Для нового пользователя используй только временный пароль, который явно задал текущий владелец или администратор.
Черновик продажи не является оплатой и не создаёт фискальный чек. Для оплаты направляй пользователя в раздел Продажи.
Основные поля действий:
клиент: client_id, full_name, phone, iin, company_name, status, category, payment, comment, address, contract_number, contract_date;
позиция: item_id, name, category, unit, description, retail_price, wholesale_price, purchase_price, discount_percent, barcode, gtin, ntin, is_marked, item_type product или service, service_sale_mode;
категория: category_id, name, markup_percent, category_type product или service;
склад: item_id, quantity, price для прихода, payment_method, comment;
задача: task_id, title, description, priority low medium high urgent, status new in_progress done cancelled, assigned_user_id, due_date;
расход: expense_id, category, description, amount, payment_method, comment, date;
документ: document_id, title, document_type invoice act waybill invoice_facture report payment check other, document_number, document_date, amount, counterparty, comment;
налоговое событие: event_id, title, description, due_date, amount;
задолженность: debt_id, title, description, due_date, amount;
пользователь: target_user_id, username, password, role owner admin employee, position, full_name, phone, percent_rate, module_codes, company_id, is_super_admin;
организация: company_id, name, bin, address, phone, iik, bik, bank, kbe, knp, director, city, business_type;
черновик продажи: client_id и items как массив объектов item_id, quantity, price или null.
Денежные суммы указывай в тенге. Не упоминай внутренние имена таблиц, company_id, SQL, API или технические детали.
""".strip()


AI_TTS_INSTRUCTIONS = """
Speak in Russian with a warm, confident adult female voice.
Sound like Nika, a thoughtful personal business assistant speaking directly to one person.
Use a calm, unhurried conversational pace, with natural pauses between ideas.
Be expressive and friendly, but restrained and professional. Never sound like an announcer,
a call-center script, a robot, or an advertisement. Clearly articulate names, numbers and amounts.
Slightly emphasize the most useful result. Do not rush lists. Keep the delivery natural and human-like.
""".strip()


# Переходы выполняются приложением, а не моделью. Так команда "открой продажи"
# работает мгновенно и не зависит от формулировки ответа AI.
NAVIGATION_TARGETS = (
    {
        "aliases": ("приход товара", "приход", "поступление товара"),
        "label": "Приход товара",
        "url": "/stock/income",
        "module": "warehouse",
    },
    {
        "aliases": ("движение товара", "движения товара", "движение по складу"),
        "label": "Движение товара",
        "url": "/stock/movements",
        "module": "warehouse",
    },
    {
        "aliases": ("списание товара", "списания", "списание"),
        "label": "Списание",
        "url": "/stock/writeoff",
        "module": "warehouse",
    },
    {
        "aliases": ("онлайн витрина", "онлайн-витрина", "витрина", "сайт магазина"),
        "label": "Онлайн-витрина",
        "url": "/storefront/",
        "module": "storefront",
        "roles": ("owner", "admin"),
    },
    {
        "aliases": ("ккм и цто", "цто", "ккм", "кассовое оборудование"),
        "label": "ККМ и ЦТО",
        "url": "/cto",
        "module": "cto",
    },
    {
        "aliases": ("подписка и модули", "подписка", "модули"),
        "label": "Подписка и модули",
        "url": "/subscription",
        "roles": ("owner",),
    },
    {
        "aliases": ("главная страница", "главная", "дашборд", "панель директора"),
        "label": "Главная",
        "url": "/dashboard",
        "module": "dashboard",
    },
    {
        "aliases": ("продажи", "продажу", "новая продажа", "касса"),
        "label": "Продажи",
        "url": "/sales",
        "module": "sales",
    },
    {
        "aliases": ("аналитика", "аналитику", "статистика"),
        "label": "Аналитика",
        "url": "/analytics",
        "module": "analytics",
    },
    {
        "aliases": ("каталог товаров", "каталог", "товары и услуги", "товары"),
        "label": "Каталог",
        "url": "/items",
        "module": "catalog",
    },
    {
        "aliases": ("задачи", "список задач"),
        "label": "Задачи",
        "url": "/tasks",
        "module": "tasks",
    },
    {
        "aliases": ("бухгалтерия", "бухгалтерию", "налоги"),
        "label": "Бухгалтерия",
        "url": "/accounting",
        "module": "accounting",
    },
    {
        "aliases": ("отчеты", "отчетность", "отчётность", "отчёты"),
        "label": "Отчёты",
        "url": "/reports",
        "module": "reports",
    },
    {
        "aliases": ("расходы", "расход"),
        "label": "Расходы",
        "url": "/expenses",
        "module": "expenses",
    },
    {
        "aliases": ("остатки на складе", "складские остатки", "остатки", "склад"),
        "label": "Остатки",
        "url": "/stock",
        "module": "warehouse",
    },
    {
        "aliases": ("клиенты", "список клиентов", "клиентская база"),
        "label": "Клиенты",
        "url": "/clients",
        "module": "clients",
    },
    {
        "aliases": ("пользователи", "сотрудники"),
        "label": "Пользователи",
        "url": "/users",
        "roles": ("owner", "admin"),
    },
    {
        "aliases": ("организации", "компании"),
        "label": "Организации",
        "url": "/companies",
        "super_admin_only": True,
    },
    {
        "aliases": ("настройки", "настройку"),
        "label": "Настройки",
        "url": "/settings",
        "module": "settings",
    },
    {
        "aliases": ("профиль", "мой профиль"),
        "label": "Профиль",
        "url": "/profile",
        "module": "profile",
    },
)


def _normalize_command(text):
    text = str(text or "").lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _can_open_target(target):
    if session.get("is_super_admin"):
        return True
    if target.get("super_admin_only"):
        return False

    role = str(session.get("role") or "").lower()
    roles = set(target.get("roles") or ())
    if role in roles:
        return True

    module = target.get("module")
    return bool(module and module in set(session.get("employee_modules") or []))


def _navigation_response(message):
    normalized = _normalize_command(message)
    navigation_verbs = (
        "открой", "открыть", "открывай", "перейди", "перейти", "переходи",
        "зайди", "зайти", "покажи раздел", "покажи страницу", "переключи",
        "переключись", "отправь меня", "веди меня",
    )
    if not any(verb in normalized for verb in navigation_verbs):
        return None

    if any(word in normalized for word in ("уведомления", "уведомление")):
        return {
            "reply": "Открываю уведомления.",
            "action": "open_drawer",
            "target": "notifications",
        }
    if any(word in normalized for word in ("общий чат", "чат", "whatsapp", "ватсап", "вотсап")):
        return {
            "reply": "Открываю чат.",
            "action": "open_drawer",
            "target": "chat",
        }

    normalized_aliases = []
    for target in NAVIGATION_TARGETS:
        for alias in target["aliases"]:
            normalized_aliases.append((_normalize_command(alias), target))

    # Сначала длинные названия: "приход товара" важнее общего слова "товары".
    normalized_aliases.sort(key=lambda pair: len(pair[0]), reverse=True)
    for alias, target in normalized_aliases:
        if re.search(rf"(?<![a-zа-я0-9]){re.escape(alias)}(?![a-zа-я0-9])", normalized):
            if not _can_open_target(target):
                return {
                    "reply": f"Раздел {target['label']} недоступен для вашей учётной записи.",
                    "action": "access_denied",
                }
            return {
                "reply": f"Открываю раздел {target['label']}.",
                "action": "redirect",
                "url": target["url"],
            }
    return None


def _plain_text_reply(text):
    """Убирает Markdown и технические символы до показа и озвучивания."""
    text = unescape(str(text or ""))
    text = re.sub(r"```(?:[a-zA-Z0-9_+-]+)?\s*([\s\S]*?)```", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-+*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__|~~|`)", "", text)
    text = re.sub(r"(?<=\d)\s*/\s*(?=\d)", " из ", text)
    text = text.replace("/", " ").replace("\\", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


AI_TOOLS = [
    {
        "type": "function",
        "name": "get_sales_summary",
        "description": "Показатели продаж: выручка, прибыль, число чеков, средний чек и способы оплаты за период.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "yesterday", "7_days", "30_days", "month"],
                    "description": "Период для расчета.",
                }
            },
            "required": ["period"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_low_stock",
        "description": "Найти товары, остаток которых ниже или равен заданному порогу.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "threshold": {"type": "integer", "minimum": 0, "maximum": 1000},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            "required": ["threshold", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_top_items",
        "description": "Лучшие товары и услуги по сумме продаж за период.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "yesterday", "7_days", "30_days", "month"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["period", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_clients",
        "description": "Найти клиента по ФИО, телефону, ИИН или названию компании.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 150},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_items",
        "description": "Найти товар или услугу по названию, штрих-коду, GTIN или NTIN.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 150},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_client_history",
        "description": "Покупки и общая сумма покупок конкретного клиента. client_id бери из search_clients.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "client_id": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["client_id", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_system_records",
        "description": "Найти задачи, пользователей, расходы, бухгалтерские записи, категории, движения склада или организации и получить их id перед действием.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "resource": {
                    "type": "string",
                    "enum": [
                        "tasks", "users", "expenses", "documents", "tax_events",
                        "debts", "categories", "stock_movements", "companies",
                    ],
                },
                "query": {"type": ["string", "null"], "maxLength": 150},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            "required": ["resource", "query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_accounting_overview",
        "description": "Сводка по расходам, задолженностям, налоговым событиям и бухгалтерским документам организации.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7_days", "30_days", "month"],
                }
            },
            "required": ["period"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "prepare_action",
        "description": "Подготовить одно изменение в Nika и показать пользователю подтверждение. Никогда не выполняет действие сразу.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(ACTION_NAMES)},
                "data_json": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 12000,
                    "description": "JSON-объект с аргументами действия. Даты в формате ГГГГ-ММ-ДД.",
                },
            },
            "required": ["action", "data_json"],
            "additionalProperties": False,
        },
    },
]


def _ensure_ai_tables():
    global _ai_tables_ready

    if _ai_tables_ready:
        return

    with AI_TABLES_LOCK:
        if _ai_tables_ready:
            return

        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_conversations (
                    id TEXT PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_messages (
                    id BIGSERIAL PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
                    company_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_conversations_owner
                ON ai_conversations(company_id, user_id, updated_at DESC)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
                ON ai_messages(conversation_id, id)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_pending_actions (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    company_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    action_name TEXT NOT NULL,
                    arguments JSONB NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMP NOT NULL,
                    confirmed_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    executed_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_pending_owner
                ON ai_pending_actions(company_id, user_id, status, created_at DESC)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_action_logs (
                    id BIGSERIAL PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    company_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    actor_role TEXT,
                    action_name TEXT NOT NULL,
                    target_type TEXT,
                    target_id INTEGER,
                    status TEXT NOT NULL,
                    request_text TEXT,
                    summary TEXT,
                    arguments JSONB,
                    before_data JSONB,
                    after_data JSONB,
                    error_text TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_action_logs_owner
                ON ai_action_logs(company_id, user_id, created_at DESC)
            """)
            cur.execute("""
                UPDATE ai_pending_actions
                SET status='expired',
                    arguments=CASE
                        WHEN arguments ? 'password'
                        THEN jsonb_set(arguments, '{password}', '"[скрыто]"'::jsonb, FALSE)
                        ELSE arguments
                    END
                WHERE status='pending' AND expires_at <= NOW()
            """)
            conn.commit()
            _ai_tables_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            pool.putconn(conn)


def _owner():
    company_id = session.get("company_id")
    user_id = session.get("user_id")
    if not user_id:
        return None, None
    # Для системного супер-администратора без выбранной организации используем
    # отдельную область 0. Данные организаций по-прежнему читаются только
    # специальными супер-админскими функциями.
    scope_company_id = int(company_id) if company_id else 0
    return scope_company_id, int(user_id)


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _period_bounds(period):
    current = now_kz()
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)

    today = current.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "yesterday":
        return today - timedelta(days=1), today, "вчера"
    if period == "7_days":
        return today - timedelta(days=6), today + timedelta(days=1), "за 7 дней"
    if period == "30_days":
        return today - timedelta(days=29), today + timedelta(days=1), "за 30 дней"
    if period == "month":
        return today.replace(day=1), today + timedelta(days=1), "за текущий месяц"
    return today, today + timedelta(days=1), "сегодня"


def _paid_sales_condition(alias="s"):
    return f"""
        {alias}.company_id = %s
        AND {alias}.created_at >= %s
        AND {alias}.created_at < %s
        AND COALESCE({alias}.is_refunded, FALSE) = FALSE
        AND (
            {alias}.paid_at IS NOT NULL
            OR COALESCE({alias}.paid_amount, 0) > 0
            OR COALESCE({alias}.status, '') IN ('Оплачено', 'РћРїР»Р°С‡РµРЅРѕ', 'paid')
        )
    """


def _query_rows(sql, params, one=False):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()
    finally:
        cur.close()
        pool.putconn(conn)


def _get_sales_summary(company_id, period):
    _require_read_module("analytics")
    if not company_id:
        raise ActionError("Сначала выберите организацию")
    start, end, label = _period_bounds(period)
    paid = _paid_sales_condition("s")
    row = _query_rows(
        f"""
        SELECT
            COALESCE(SUM(s.total_amount), 0) AS revenue,
            COUNT(*) AS sales_count,
            COALESCE(AVG(s.total_amount), 0) AS average_check,
            COALESCE(SUM(s.cash_amount), 0) AS cash,
            COALESCE(SUM(s.card_amount), 0) AS card,
            COALESCE(SUM(s.kaspi_amount), 0) AS kaspi,
            COALESCE(SUM((
                SELECT COALESCE(SUM(si.profit), 0)
                FROM sale_items si
                WHERE si.sale_id = s.id
            )), 0) AS profit
        FROM sales s
        WHERE {paid}
        """,
        (company_id, start, end),
        one=True,
    )
    return {"period": label, **dict(row or {})}


def _get_low_stock(company_id, threshold, limit):
    _require_read_module("warehouse")
    if not company_id:
        raise ActionError("Сначала выберите организацию")
    rows = _query_rows(
        """
        WITH stock_rows AS (
            SELECT i.id, i.name, i.unit, i.retail_price, i.barcode,
                   COALESCE(SUM(
                       CASE
                           WHEN sm.movement_type IN ('income', 'refund') THEN sm.quantity
                           WHEN sm.movement_type IN ('sale', 'writeoff') THEN -sm.quantity
                           ELSE 0
                       END
                   ), 0) AS quantity
            FROM items i
            LEFT JOIN stock_movements sm
              ON sm.item_id = i.id AND sm.company_id = i.company_id
            WHERE i.company_id = %s
              AND COALESCE(i.item_type, 'product') = 'product'
            GROUP BY i.id
        )
        SELECT * FROM stock_rows
        WHERE quantity <= %s
        ORDER BY quantity, name
        LIMIT %s
        """,
        (company_id, max(0, int(threshold)), min(30, max(1, int(limit)))),
    )
    return {"threshold": threshold, "count": len(rows), "items": [dict(row) for row in rows]}


def _get_top_items(company_id, period, limit):
    _require_read_module("analytics")
    if not company_id:
        raise ActionError("Сначала выберите организацию")
    start, end, label = _period_bounds(period)
    paid = _paid_sales_condition("s")
    rows = _query_rows(
        f"""
        SELECT COALESCE(si.name, i.name, 'Без названия') AS name,
               COALESCE(SUM(si.quantity), 0) AS quantity,
               COALESCE(SUM(si.total), 0) AS total
        FROM sale_items si
        JOIN sales s ON s.id = si.sale_id
        LEFT JOIN items i ON i.id = si.item_id AND i.company_id = s.company_id
        WHERE {paid}
        GROUP BY COALESCE(si.name, i.name, 'Без названия')
        ORDER BY total DESC
        LIMIT %s
        """,
        (company_id, start, end, min(20, max(1, int(limit)))),
    )
    return {"period": label, "count": len(rows), "items": [dict(row) for row in rows]}


def _search_clients(company_id, query, limit):
    _require_read_module("clients")
    if not company_id:
        raise ActionError("Сначала выберите организацию")
    query = str(query).strip()[:150]
    digits = "".join(character for character in query if character.isdigit())
    rows = _query_rows(
        """
        SELECT id, full_name, phone, company_name, iin, status, category
        FROM clients
        WHERE company_id = %s
          AND COALESCE(is_deleted, FALSE) = FALSE
          AND (
              COALESCE(full_name, '') ILIKE %s
              OR COALESCE(company_name, '') ILIKE %s
              OR COALESCE(iin, '') LIKE %s
              OR (%s <> '' AND regexp_replace(COALESCE(phone, ''), '\\D', '', 'g') LIKE %s)
          )
        ORDER BY full_name
        LIMIT %s
        """,
        (
            company_id,
            f"%{query}%",
            f"%{query}%",
            f"%{digits or query}%",
            digits,
            f"%{digits}%",
            min(20, max(1, int(limit))),
        ),
    )
    return {"query": query, "count": len(rows), "clients": [dict(row) for row in rows]}


def _search_items(company_id, query, limit):
    _require_read_module("catalog")
    if not company_id:
        raise ActionError("Сначала выберите организацию")
    query = str(query).strip()[:150]
    rows = _query_rows(
        """
        SELECT id, name, retail_price, purchase_price, quantity, unit, barcode,
               gtin, ntin, COALESCE(item_type, 'product') AS item_type
        FROM items
        WHERE company_id = %s
          AND (
              COALESCE(name, '') ILIKE %s
              OR COALESCE(barcode, '') LIKE %s
              OR COALESCE(gtin, '') LIKE %s
              OR COALESCE(ntin, '') LIKE %s
          )
        ORDER BY
            CASE WHEN barcode = %s OR gtin = %s OR ntin = %s THEN 0 ELSE 1 END,
            name
        LIMIT %s
        """,
        (
            company_id,
            f"%{query}%",
            f"%{query}%",
            f"%{query}%",
            f"%{query}%",
            query,
            query,
            query,
            min(20, max(1, int(limit))),
        ),
    )
    return {"query": query, "count": len(rows), "items": [dict(row) for row in rows]}


def _get_client_history(company_id, client_id, limit):
    _require_read_module("clients")
    if not company_id:
        raise ActionError("Сначала выберите организацию")
    client = _query_rows(
        """
        SELECT id, full_name, phone, company_name
        FROM clients
        WHERE id = %s AND company_id = %s AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (int(client_id), company_id),
        one=True,
    )
    if not client:
        return {"found": False}

    rows = _query_rows(
        """
        SELECT s.id, s.sale_number, s.total_amount, s.paid_amount, s.status, s.created_at,
               COALESCE(string_agg(COALESCE(si.name, ''), ', ' ORDER BY si.id), '') AS items
        FROM sales s
        LEFT JOIN sale_items si ON si.sale_id = s.id
        WHERE s.company_id = %s AND s.client_id = %s
        GROUP BY s.id
        ORDER BY s.created_at DESC
        LIMIT %s
        """,
        (company_id, int(client_id), min(20, max(1, int(limit)))),
    )
    total = sum((row.get("total_amount") or 0) for row in rows)
    return {
        "found": True,
        "client": dict(client),
        "shown_sales": len(rows),
        "shown_total": total,
        "sales": [dict(row) for row in rows],
    }


def _require_read_module(module):
    if session.get("is_super_admin"):
        return
    if module == "users" and session.get("role") in ("owner", "admin"):
        return
    if module not in set(session.get("employee_modules") or []):
        raise PermissionDenied("У вашей учётной записи нет доступа к этому разделу")


def _search_system_records(company_id, resource, query, limit):
    query = str(query or "").strip()[:150]
    limit = min(30, max(1, int(limit)))
    pattern = f"%{query}%"

    resource_modules = {
        "tasks": "tasks",
        "expenses": "expenses",
        "documents": "accounting",
        "tax_events": "accounting",
        "debts": "accounting",
        "categories": "catalog",
        "stock_movements": "warehouse",
        "users": "users",
    }

    if resource == "companies":
        if not session.get("is_super_admin"):
            raise PermissionDenied("Организации доступны только супер-администратору")
        rows = _query_rows(
            """
            SELECT id, name, bin, phone, city, director, is_active
            FROM companies
            WHERE (%s = '' OR COALESCE(name, '') ILIKE %s OR COALESCE(bin, '') ILIKE %s)
            ORDER BY id DESC LIMIT %s
            """,
            (query, pattern, pattern, limit),
        )
        return {"resource": resource, "count": len(rows), "items": [dict(row) for row in rows]}

    _require_read_module(resource_modules[resource])
    if not company_id:
        raise ActionError("Сначала выберите организацию")

    if resource in {"documents", "tax_events", "debts"}:
        from routes.accounting import _ensure_accounting_tables
        conn = get_db()
        cur = conn.cursor()
        try:
            _ensure_accounting_tables(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            pool.putconn(conn)

    if resource == "tasks":
        rows = _query_rows(
            """
            SELECT t.id, t.title, t.description, t.priority, t.status, t.due_date,
                   t.assigned_user_id, u.full_name AS assigned_user
            FROM tasks t LEFT JOIN users u ON u.id = t.assigned_user_id
            WHERE t.company_id = %s
              AND (%s = '' OR COALESCE(t.title, '') ILIKE %s OR COALESCE(t.description, '') ILIKE %s)
            ORDER BY t.id DESC LIMIT %s
            """,
            (company_id, query, pattern, pattern, limit),
        )
    elif resource == "users":
        if session.get("is_super_admin") and company_id == 0:
            rows = _query_rows(
                """
                SELECT u.id, u.username, u.full_name, u.phone, u.position, u.role,
                       u.company_id, u.is_super_admin, c.name AS company_name
                FROM users u LEFT JOIN companies c ON c.id = u.company_id
                WHERE (%s = '' OR COALESCE(u.username, '') ILIKE %s OR COALESCE(u.full_name, '') ILIKE %s)
                ORDER BY u.id DESC LIMIT %s
                """,
                (query, pattern, pattern, limit),
            )
        else:
            rows = _query_rows(
                """
                SELECT id, username, full_name, phone, position, role, company_id, is_super_admin
                FROM users WHERE company_id = %s
                  AND (%s = '' OR COALESCE(username, '') ILIKE %s OR COALESCE(full_name, '') ILIKE %s)
                ORDER BY id DESC LIMIT %s
                """,
                (company_id, query, pattern, pattern, limit),
            )
    elif resource == "expenses":
        rows = _query_rows(
            """
            SELECT id, category, description, amount, payment_method, date, source_type
            FROM expenses WHERE company_id = %s
              AND (%s = '' OR COALESCE(description, '') ILIKE %s OR COALESCE(category, '') ILIKE %s)
            ORDER BY date DESC, id DESC LIMIT %s
            """,
            (company_id, query, pattern, pattern, limit),
        )
    elif resource == "documents":
        rows = _query_rows(
            """
            SELECT id, title, document_type, document_number, document_date, amount,
                   counterparty, status, source_type
            FROM accounting_documents WHERE company_id = %s
              AND (%s = '' OR COALESCE(title, '') ILIKE %s OR COALESCE(counterparty, '') ILIKE %s)
            ORDER BY document_date DESC, id DESC LIMIT %s
            """,
            (company_id, query, pattern, pattern, limit),
        )
    elif resource == "tax_events":
        rows = _query_rows(
            """
            SELECT id, title, description, due_date, amount, status, paid_at
            FROM accounting_tax_events WHERE company_id = %s
              AND (%s = '' OR COALESCE(title, '') ILIKE %s OR COALESCE(description, '') ILIKE %s)
            ORDER BY due_date, id DESC LIMIT %s
            """,
            (company_id, query, pattern, pattern, limit),
        )
    elif resource == "debts":
        rows = _query_rows(
            """
            SELECT id, title, description, due_date, amount, status, paid_at
            FROM accounting_debts WHERE company_id = %s
              AND (%s = '' OR COALESCE(title, '') ILIKE %s OR COALESCE(description, '') ILIKE %s)
            ORDER BY due_date, id DESC LIMIT %s
            """,
            (company_id, query, pattern, pattern, limit),
        )
    elif resource == "categories":
        rows = _query_rows(
            """
            SELECT id, name, markup_percent, category_type
            FROM categories WHERE company_id = %s
              AND (%s = '' OR COALESCE(name, '') ILIKE %s)
            ORDER BY name LIMIT %s
            """,
            (company_id, query, pattern, limit),
        )
    else:
        rows = _query_rows(
            """
            SELECT sm.id, sm.item_id, i.name AS item_name, sm.movement_type,
                   sm.quantity, sm.price, sm.total, sm.comment, sm.created_at
            FROM stock_movements sm
            JOIN items i ON i.id = sm.item_id AND i.company_id = sm.company_id
            WHERE sm.company_id = %s
              AND (%s = '' OR COALESCE(i.name, '') ILIKE %s OR COALESCE(sm.comment, '') ILIKE %s)
            ORDER BY sm.id DESC LIMIT %s
            """,
            (company_id, query, pattern, pattern, limit),
        )

    return {"resource": resource, "count": len(rows), "items": [dict(row) for row in rows]}


def _get_accounting_overview(company_id, period):
    _require_read_module("accounting")
    if not company_id:
        raise ActionError("Сначала выберите организацию")
    from routes.accounting import _ensure_accounting_tables
    from routes.expenses import _ensure_expenses_table
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        _ensure_expenses_table(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)
    start, end, label = _period_bounds(period)
    row = _query_rows(
        """
        SELECT
            COALESCE((SELECT SUM(amount) FROM expenses WHERE company_id=%s AND date >= %s::date AND date < %s::date), 0) AS expenses,
            COALESCE((SELECT SUM(amount) FROM accounting_debts WHERE company_id=%s AND status <> 'paid'), 0) AS debts_due,
            COALESCE((SELECT COUNT(*) FROM accounting_debts WHERE company_id=%s AND status <> 'paid'), 0) AS debts_count,
            COALESCE((SELECT SUM(amount) FROM accounting_tax_events WHERE company_id=%s AND status <> 'paid'), 0) AS taxes_due,
            COALESCE((SELECT COUNT(*) FROM accounting_documents WHERE company_id=%s AND status='active'), 0) AS active_documents
        """,
        (company_id, start, end, company_id, company_id, company_id, company_id),
        one=True,
    )
    return {"period": label, **dict(row or {})}


def _redact_arguments(arguments):
    clean = dict(arguments or {})
    for key in ("password", "token", "api_key", "secret"):
        if key in clean:
            clean[key] = "[скрыто]"
    return clean


def _create_pending_action(conversation_id, company_id, user_id, action, data_json, request_text):
    try:
        raw_data = json.loads(data_json or "{}")
    except json.JSONDecodeError:
        raise ActionError("Не удалось разобрать данные действия")
    if not isinstance(raw_data, dict):
        raise ActionError("Данные действия должны быть объектом")

    prepared = prepare_action(action, raw_data)
    safe_request_text = request_text[:4000]
    if "password" in prepared["arguments"]:
        safe_request_text = "[текст скрыт: команда содержала пароль]"
    action_id = str(uuid.uuid4())
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE ai_pending_actions
            SET status='cancelled', cancelled_at=%s
            WHERE company_id=%s AND user_id=%s AND status='pending'
            """,
            (now_kz(), company_id, user_id),
        )
        cur.execute(
            """
            INSERT INTO ai_pending_actions (
                id, conversation_id, company_id, user_id, action_name,
                arguments, summary, status, created_at, expires_at
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,'pending',%s,%s + INTERVAL '10 minutes')
            """,
            (
                action_id, conversation_id, company_id, user_id, action,
                json.dumps(prepared["arguments"], ensure_ascii=False, default=_json_default),
                prepared["summary"], now_kz(), now_kz(),
            ),
        )
        cur.execute(
            """
            INSERT INTO ai_action_logs (
                action_id,company_id,user_id,actor_role,action_name,status,
                request_text,summary,arguments,created_at
            ) VALUES (%s,%s,%s,%s,%s,'pending',%s,%s,%s::jsonb,%s)
            """,
            (
                action_id, company_id, user_id, session.get("role"), action,
                safe_request_text, prepared["summary"],
                json.dumps(_redact_arguments(prepared["arguments"]), ensure_ascii=False, default=_json_default),
                now_kz(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)

    return {
        "id": action_id,
        "summary": prepared["summary"],
        "expires_in_seconds": 600,
        "sensitive": "password" in prepared["arguments"],
    }


def _latest_pending_action(company_id, user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE ai_pending_actions
            SET status='expired',
                arguments=CASE WHEN arguments ? 'password'
                    THEN jsonb_set(arguments, '{password}', '"[скрыто]"'::jsonb, FALSE)
                    ELSE arguments END
            WHERE company_id=%s AND user_id=%s AND status='pending' AND expires_at <= NOW()
            """,
            (company_id, user_id),
        )
        cur.execute(
            """
            SELECT id, summary, action_name
            FROM ai_pending_actions
            WHERE company_id=%s AND user_id=%s AND status='pending' AND expires_at > NOW()
            ORDER BY created_at DESC LIMIT 1
            """,
            (company_id, user_id),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _record_action_result(action_row, status, result=None, error_text=None):
    result = result or {}
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE ai_pending_actions
            SET status=%s,
                executed_at=CASE WHEN %s='executed' THEN %s ELSE executed_at END,
                cancelled_at=CASE WHEN %s='cancelled' THEN %s ELSE cancelled_at END,
                arguments=%s::jsonb
            WHERE id=%s AND company_id=%s AND user_id=%s
            """,
            (
                status, status, now_kz(), status, now_kz(),
                json.dumps(_redact_arguments(action_row.get("arguments") or {}), ensure_ascii=False, default=_json_default),
                action_row["id"], action_row["company_id"], action_row["user_id"],
            ),
        )
        cur.execute(
            """
            INSERT INTO ai_action_logs (
                action_id,company_id,user_id,actor_role,action_name,target_type,
                target_id,status,summary,arguments,before_data,after_data,error_text,created_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)
            """,
            (
                action_row["id"], action_row["company_id"], action_row["user_id"],
                session.get("role"), action_row["action_name"], result.get("target_type"),
                result.get("target_id"), status, action_row.get("summary"),
                json.dumps(_redact_arguments(action_row.get("arguments") or {}), ensure_ascii=False, default=_json_default),
                json.dumps(result.get("before"), ensure_ascii=False, default=_json_default) if result.get("before") is not None else None,
                json.dumps(result.get("after"), ensure_ascii=False, default=_json_default) if result.get("after") is not None else None,
                str(error_text or "")[:2000] or None, now_kz(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        current_app.logger.exception("Nika AI action log failed")
    finally:
        cur.close()
        pool.putconn(conn)


def _claim_pending_action(action_id, company_id, user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE ai_pending_actions
            SET status='executing', confirmed_at=%s
            WHERE id=%s AND company_id=%s AND user_id=%s
              AND status='pending' AND expires_at > NOW()
            RETURNING *
            """,
            (now_kz(), action_id, company_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                UPDATE ai_pending_actions
                SET status='expired',
                    arguments=CASE WHEN arguments ? 'password'
                        THEN jsonb_set(arguments, '{password}', '"[скрыто]"'::jsonb, FALSE)
                        ELSE arguments END
                WHERE id=%s AND company_id=%s AND user_id=%s
                  AND status='pending' AND expires_at <= NOW()
                """,
                (action_id, company_id, user_id),
            )
        conn.commit()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _execute_pending_action(action_id, company_id, user_id):
    action_row = _claim_pending_action(action_id, company_id, user_id)
    if not action_row:
        raise ActionError("Подтверждение уже использовано, отменено или просрочено")
    try:
        result = execute_action(action_row["action_name"], dict(action_row["arguments"] or {}))
        _record_action_result(action_row, "executed", result=result)
        return result
    except (ActionError, PermissionDenied) as error:
        _record_action_result(action_row, "failed", error_text=str(error))
        raise
    except Exception as error:
        _record_action_result(action_row, "failed", error_text="Внутренняя ошибка выполнения")
        raise


def _cancel_pending_action(action_id, company_id, user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE ai_pending_actions
            SET status='cancelled', cancelled_at=%s
            WHERE id=%s AND company_id=%s AND user_id=%s AND status='pending'
            RETURNING *
            """,
            (now_kz(), action_id, company_id, user_id),
        )
        row = cur.fetchone()
        conn.commit()
        if not row:
            raise ActionError("Действие уже выполнено, отменено или просрочено")
        action_row = dict(row)
        _record_action_result(action_row, "cancelled")
        return action_row
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _execute_tool(name, arguments, company_id, conversation_id=None, user_id=None, request_text=""):
    if name == "get_sales_summary":
        return _get_sales_summary(company_id, arguments["period"])
    if name == "get_low_stock":
        return _get_low_stock(company_id, arguments["threshold"], arguments["limit"])
    if name == "get_top_items":
        return _get_top_items(company_id, arguments["period"], arguments["limit"])
    if name == "search_clients":
        return _search_clients(company_id, arguments["query"], arguments["limit"])
    if name == "search_items":
        return _search_items(company_id, arguments["query"], arguments["limit"])
    if name == "get_client_history":
        return _get_client_history(company_id, arguments["client_id"], arguments["limit"])
    if name == "search_system_records":
        return _search_system_records(
            company_id, arguments["resource"], arguments.get("query"), arguments["limit"]
        )
    if name == "get_accounting_overview":
        return _get_accounting_overview(company_id, arguments["period"])
    if name == "prepare_action":
        if not conversation_id or not user_id:
            raise ActionError("Не удалось подготовить подтверждение")
        return {
            "pending_action": _create_pending_action(
                conversation_id,
                company_id,
                user_id,
                arguments["action"],
                arguments["data_json"],
                request_text,
            )
        }
    return {"error": "Функция не поддерживается"}


def _get_or_create_conversation(company_id, user_id, requested_id=None):
    conn = get_db()
    cur = conn.cursor()
    try:
        if requested_id:
            cur.execute(
                """
                SELECT id FROM ai_conversations
                WHERE id = %s AND company_id = %s AND user_id = %s
                """,
                (str(requested_id)[:80], company_id, user_id),
            )
            row = cur.fetchone()
            if row:
                return row["id"]

        conversation_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ai_conversations (id, company_id, user_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, company_id, user_id, now_kz(), now_kz()),
        )
        conn.commit()
        return conversation_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _load_messages(conversation_id, company_id, user_id, limit=AI_MAX_HISTORY):
    rows = _query_rows(
        """
        SELECT role, content
        FROM (
            SELECT id, role, content
            FROM ai_messages
            WHERE conversation_id = %s AND company_id = %s AND user_id = %s
            ORDER BY id DESC
            LIMIT %s
        ) recent
        ORDER BY id
        """,
        (conversation_id, company_id, user_id, limit),
    )
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def _save_exchange(conversation_id, company_id, user_id, user_text, reply):
    conn = get_db()
    cur = conn.cursor()
    try:
        timestamp = now_kz()
        cur.executemany(
            """
            INSERT INTO ai_messages
                (conversation_id, company_id, user_id, role, content, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (conversation_id, company_id, user_id, "user", user_text, timestamp),
                (conversation_id, company_id, user_id, "assistant", reply, timestamp),
            ],
        )
        cur.execute(
            """
            UPDATE ai_conversations SET updated_at = %s
            WHERE id = %s AND company_id = %s AND user_id = %s
            """,
            (timestamp, conversation_id, company_id, user_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _create_ai_response(request_options):
    """Повторяет только временные API/сетевые сбои, каждый раз через новое соединение."""
    retryable_statuses = {408, 409, 429, 500, 502, 503, 504}

    for attempt in range(1, AI_REQUEST_ATTEMPTS + 1):
        try:
            # Новое соединение особенно важно после повреждения текущего TLS-канала
            # (например, SSLV3_ALERT_BAD_RECORD_MAC на нестабильной сети Windows).
            with OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                timeout=45.0,
                max_retries=0,
            ) as client:
                return client.responses.create(**request_options)
        except APIStatusError as error:
            if error.status_code not in retryable_statuses or attempt == AI_REQUEST_ATTEMPTS:
                raise
            delay = 0.75 * (2 ** (attempt - 1))
            current_app.logger.warning(
                "Nika AI temporary API error %s; retry %s/%s in %.2fs",
                error.status_code,
                attempt + 1,
                AI_REQUEST_ATTEMPTS,
                delay,
            )
            time.sleep(delay)
        except APIConnectionError as error:
            if attempt == AI_REQUEST_ATTEMPTS:
                raise
            delay = 0.75 * (2 ** (attempt - 1))
            current_app.logger.warning(
                "Nika AI temporary connection error (%s); retry %s/%s in %.2fs",
                type(error.__cause__).__name__ if error.__cause__ else type(error).__name__,
                attempt + 1,
                AI_REQUEST_ATTEMPTS,
                delay,
            )
            time.sleep(delay)


def _generate_reply(message, history, company_id, user_id, conversation_id):

    input_items = [*history, {"role": "user", "content": message}]

    for _ in range(AI_MAX_TOOL_ROUNDS):
        request_options = {
            "model": AI_MODEL,
            "instructions": AI_INSTRUCTIONS,
            "input": input_items,
            "tools": AI_TOOLS,
            "store": False,
            "max_output_tokens": 900,
            "parallel_tool_calls": False,
        }
        if AI_MODEL.startswith("gpt-5.6"):
            request_options["reasoning"] = {"effort": "none"}

        response = _create_ai_response(request_options)

        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            reply = _plain_text_reply(response.output_text)
            return reply or "Не удалось сформировать ответ. Попробуйте задать вопрос иначе.", None

        input_items += response.output

        for tool_call in function_calls:
            try:
                arguments = json.loads(tool_call.arguments or "{}")
                result = _execute_tool(
                    tool_call.name,
                    arguments,
                    company_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    request_text=message,
                )
                if result.get("pending_action"):
                    pending = result["pending_action"]
                    return (
                        f"Я подготовила действие: {pending['summary']}. Проверьте детали и подтвердите выполнение.",
                        pending,
                    )
            except (ActionError, PermissionDenied) as error:
                result = {"error": str(error)}
            except Exception:
                current_app.logger.exception("Nika AI tool failed: %s", tool_call.name)
                result = {"error": "Не удалось получить данные"}

            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(result, ensure_ascii=False, default=_json_default),
                }
            )

    return "Запрос оказался слишком сложным. Уточните, какие именно данные нужны.", None


def _confirmation_intent(message):
    normalized = _normalize_command(message)
    confirm_phrases = {
        "подтверждаю", "да подтверждаю", "подтвердить", "выполняй",
        "выполни действие", "можно выполнять", "согласен", "согласна",
    }
    cancel_phrases = {
        "отмена", "отмени", "отменить действие", "не выполняй", "не надо",
    }
    if normalized in confirm_phrases:
        return "confirm"
    if normalized in cancel_phrases:
        return "cancel"
    return None


@ai_bp.route("/api/ai/history", methods=["GET"])
def ai_history():
    company_id, user_id = _owner()
    if company_id is None or not user_id:
        return jsonify({"error": "Требуется вход в систему"}), 401

    try:
        _ensure_ai_tables()
        limit = min(100, max(1, request.args.get("limit", 50, type=int)))
        conversation = _query_rows(
            """
            SELECT id FROM ai_conversations
            WHERE company_id = %s AND user_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (company_id, user_id),
            one=True,
        )

        if not conversation:
            return jsonify({"conversation_id": None, "items": []})

        conversation_id = conversation["id"]
        pending = _latest_pending_action(company_id, user_id)
        return jsonify(
            {
                "conversation_id": conversation_id,
                "items": _load_messages(
                    conversation_id,
                    company_id,
                    user_id,
                    limit=limit,
                ),
                "confirmation": {
                    "id": pending["id"],
                    "summary": pending["summary"],
                } if pending else None,
            }
        )
    except Exception:
        current_app.logger.exception("Nika AI history failed")
        return jsonify({"error": "Не удалось загрузить историю AI"}), 500


@ai_bp.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    company_id, user_id = _owner()
    if company_id is None or not user_id:
        return jsonify({"error": "Требуется вход в систему"}), 401

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or payload.get("text") or "").strip()
    if not message:
        return jsonify({"error": "Напишите вопрос"}), 400
    if len(message) > 4000:
        return jsonify({"error": "Сообщение слишком длинное"}), 400

    try:
        _ensure_ai_tables()
        conversation_id = _get_or_create_conversation(
            company_id,
            user_id,
            payload.get("conversation_id"),
        )

        intent = _confirmation_intent(message)
        if intent:
            pending = _latest_pending_action(company_id, user_id)
            if not pending:
                reply = "У вас нет действия, ожидающего подтверждения."
                _save_exchange(conversation_id, company_id, user_id, message, reply)
                return jsonify({"reply": reply, "conversation_id": conversation_id})
            if intent == "cancel":
                _cancel_pending_action(pending["id"], company_id, user_id)
                reply = f"Отменила действие: {pending['summary']}."
            else:
                result = _execute_pending_action(pending["id"], company_id, user_id)
                reply = result["message"]
            _save_exchange(conversation_id, company_id, user_id, message, reply)
            return jsonify({
                "reply": reply,
                "conversation_id": conversation_id,
                "action_status": "cancelled" if intent == "cancel" else "executed",
            })

        navigation = _navigation_response(message)
        if navigation:
            return jsonify(navigation)

        if not os.getenv("OPENAI_API_KEY"):
            return jsonify({"error": "Nika AI ещё не подключён на сервере"}), 503

        history = _load_messages(conversation_id, company_id, user_id)
        reply, pending = _generate_reply(
            message, history, company_id, user_id, conversation_id
        )
        saved_message = "[команда с паролем скрыта]" if pending and pending.get("sensitive") else message
        _save_exchange(conversation_id, company_id, user_id, saved_message, reply)
        response = {"reply": reply, "conversation_id": conversation_id}
        if pending:
            response["confirmation"] = pending
        return jsonify(response)
    except (ActionError, PermissionDenied) as error:
        return jsonify({"error": str(error)}), 403 if isinstance(error, PermissionDenied) else 400
    except Exception:
        current_app.logger.exception("Nika AI chat failed")
        return jsonify({"error": "Nika AI временно недоступен. Попробуйте ещё раз"}), 503


@ai_bp.route("/api/ai/action/<action_id>", methods=["POST"])
def ai_action(action_id):
    company_id, user_id = _owner()
    if company_id is None or not user_id:
        return jsonify({"error": "Требуется вход в систему"}), 401

    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"confirm", "cancel"}:
        return jsonify({"error": "Неизвестное решение"}), 400

    try:
        _ensure_ai_tables()
        if decision == "cancel":
            action_row = _cancel_pending_action(action_id, company_id, user_id)
            return jsonify({
                "reply": f"Отменила действие: {action_row['summary']}.",
                "status": "cancelled",
            })

        result = _execute_pending_action(action_id, company_id, user_id)
        return jsonify({"reply": result["message"], "status": "executed"})
    except PermissionDenied as error:
        return jsonify({"error": str(error)}), 403
    except ActionError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        current_app.logger.exception("Nika AI action failed")
        return jsonify({"error": "Не удалось выполнить действие"}), 500


@ai_bp.route("/api/ai/voice", methods=["POST"])
def ai_voice():
    """Создаёт естественную озвучку ответа; ключ OpenAI остаётся только на сервере."""
    company_id, user_id = _owner()
    if company_id is None or not user_id:
        return jsonify({"error": "Требуется вход в систему"}), 401

    payload = request.get_json(silent=True) or {}
    text = _plain_text_reply(payload.get("text"))
    if not text:
        return jsonify({"error": "Нет текста для озвучивания"}), 400
    if len(text) > 4000:
        text = text[:4000].rsplit(" ", 1)[0].rstrip(" ,;:") + "."

    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "AI-озвучивание ещё не подключено"}), 503

    try:
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=45.0,
            max_retries=1,
        )
        with client.audio.speech.with_streaming_response.create(
            model=AI_TTS_MODEL,
            voice=AI_TTS_VOICE,
            input=text,
            instructions=AI_TTS_INSTRUCTIONS,
            response_format="mp3",
            speed=0.94,
        ) as audio_response:
            audio_bytes = audio_response.read()

        return Response(
            audio_bytes,
            mimetype="audio/mpeg",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": "inline; filename=nika-voice.mp3",
            },
        )
    except Exception:
        current_app.logger.exception("Nika AI voice failed")
        return jsonify({"error": "AI-озвучивание временно недоступно"}), 503
