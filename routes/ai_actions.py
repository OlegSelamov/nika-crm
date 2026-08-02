"""Безопасные изменяющие действия для Nika AI 2.0.

Модель никогда не получает прямой доступ к SQL. Она может только подготовить
одно из перечисленных здесь действий. Сервер повторно проверяет роль,
разрешённый модуль, company_id и состояние записи как при подготовке, так и
непосредственно перед выполнением после подтверждения пользователя.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from flask import session

from models import get_db, pool
from utils.timezone import now_kz


class ActionError(Exception):
    """Понятная пользователю ошибка действия."""


class PermissionDenied(ActionError):
    """Действие запрещено текущей учётной записи."""


ACTION_NAMES = (
    "create_client",
    "update_client",
    "archive_client",
    "restore_client",
    "delete_client_permanently",
    "send_client_whatsapp",
    "create_item",
    "update_item",
    "delete_item",
    "create_category",
    "update_category",
    "delete_category",
    "stock_income",
    "stock_writeoff",
    "create_task",
    "update_task",
    "change_task_status",
    "delete_task",
    "create_expense",
    "update_expense",
    "delete_expense",
    "create_accounting_document",
    "update_accounting_document",
    "archive_accounting_document",
    "delete_accounting_document",
    "create_tax_event",
    "mark_tax_event_paid",
    "delete_tax_event",
    "create_debt",
    "mark_debt_paid",
    "delete_debt",
    "create_user",
    "update_user",
    "delete_user",
    "create_company",
    "update_company",
    "delete_company",
    "activate_company",
    "create_sale_draft",
)


ACTION_MODULES = {
    "create_client": "clients",
    "update_client": "clients",
    "archive_client": "clients",
    "restore_client": "clients",
    "delete_client_permanently": "clients",
    "send_client_whatsapp": "clients",
    "create_item": "catalog",
    "update_item": "catalog",
    "delete_item": "catalog",
    "create_category": "catalog",
    "update_category": "catalog",
    "delete_category": "catalog",
    "stock_income": "warehouse",
    "stock_writeoff": "warehouse",
    "create_task": "tasks",
    "update_task": "tasks",
    "change_task_status": "tasks",
    "delete_task": "tasks",
    "create_expense": "expenses",
    "update_expense": "expenses",
    "delete_expense": "expenses",
    "create_accounting_document": "accounting",
    "update_accounting_document": "accounting",
    "archive_accounting_document": "accounting",
    "delete_accounting_document": "accounting",
    "create_tax_event": "accounting",
    "mark_tax_event_paid": "accounting",
    "delete_tax_event": "accounting",
    "create_debt": "accounting",
    "mark_debt_paid": "accounting",
    "delete_debt": "accounting",
    "create_sale_draft": "sales",
}


OWNER_ACTIONS = {
    "create_user",
    "update_user",
    "delete_user",
    "delete_client_permanently",
}


SUPER_ADMIN_ACTIONS = {
    "create_company",
    "update_company",
    "delete_company",
    "activate_company",
}


EXPENSE_CATEGORIES = {
    "Аренда",
    "Зарплата",
    "Транспорт",
    "Закупки",
    "Коммунальные",
    "Налоги и обязательные платежи",
    "Комиссии",
    "Реклама",
    "Оборудование",
    "Доставка",
    "Прочие расходы",
}

PAYMENT_METHODS = {
    "Наличные",
    "Банковская карта",
    "Kaspi",
    "Расчётный счёт",
    "Другое",
}

DOCUMENT_TYPES = {
    "invoice",
    "act",
    "waybill",
    "invoice_facture",
    "report",
    "payment",
    "check",
    "other",
}

TASK_PRIORITIES = {"low", "medium", "high", "urgent"}
TASK_STATUSES = {"new", "in_progress", "done", "cancelled"}
USER_ROLES = {"owner", "admin", "employee"}


def _role() -> str:
    return str(session.get("role") or "employee").lower()


def _is_super_admin() -> bool:
    return bool(session.get("is_super_admin"))


def _is_root_admin() -> bool:
    return _is_super_admin() and session.get("username") == "admin"


def _company_id(required: bool = True) -> int | None:
    value = session.get("company_id")
    if value in (None, ""):
        if required:
            raise PermissionDenied("Сначала выберите организацию")
        return None
    return int(value)


def _user_id() -> int:
    value = session.get("user_id")
    if not value:
        raise PermissionDenied("Требуется вход в систему")
    return int(value)


def _require_action_access(action: str) -> None:
    if action not in ACTION_NAMES:
        raise ActionError("Это действие Nika пока не поддерживает")

    if _is_super_admin():
        return

    if action in SUPER_ADMIN_ACTIONS:
        raise PermissionDenied("Это действие доступно только супер-администратору")

    if action in OWNER_ACTIONS and _role() not in {"owner", "admin"}:
        raise PermissionDenied("Для этого действия нужны права владельца или администратора")

    module = ACTION_MODULES.get(action)
    if module and module not in set(session.get("employee_modules") or []):
        raise PermissionDenied("У вашей учётной записи нет доступа к этому разделу")


def _text(data: dict[str, Any], key: str, *, required: bool = False, limit: int = 500) -> str:
    value = str(data.get(key) or "").strip()
    if required and not value:
        raise ActionError(f"Не заполнено поле: {key}")
    return value[:limit]


def _integer(data: dict[str, Any], key: str, *, required: bool = True, minimum: int = 1) -> int | None:
    value = data.get(key)
    if value in (None, "") and not required:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ActionError(f"Некорректное значение: {key}")
    if result < minimum:
        raise ActionError(f"Некорректное значение: {key}")
    return result


def _number(
    data: dict[str, Any],
    key: str,
    *,
    required: bool = True,
    minimum: Decimal = Decimal("0"),
) -> Decimal | None:
    value = data.get(key)
    if value in (None, "") and not required:
        return None
    try:
        result = Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ActionError(f"Некорректное число: {key}")
    if result < minimum:
        raise ActionError(f"Значение {key} не может быть меньше {minimum}")
    return result.quantize(Decimal("0.01"))


def _date(data: dict[str, Any], key: str, *, required: bool = True):
    value = _text(data, key, required=required, limit=10)
    if not value and not required:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ActionError(f"Дата {key} должна быть в формате ГГГГ-ММ-ДД")


def _row(cur, sql: str, params: tuple[Any, ...], not_found: str):
    cur.execute(sql, params)
    value = cur.fetchone()
    if not value:
        raise ActionError(not_found)
    return dict(value)


def _clean_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    cleaned = dict(row)
    cleaned.pop("password", None)
    return cleaned


def _allowed_fields(data: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key in fields}


def _normalized_phone(phone: Any) -> str:
    digits = "".join(character for character in str(phone or "") if character.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def _resolve_message_recipient(
    company_id: int,
    recipient_query: str,
    expected_client_id: int,
) -> dict[str, Any]:
    """Resolve one client without letting the model guess between similar names."""
    query = str(recipient_query or "").strip()[:180]
    digits = _normalized_phone(query)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, full_name, phone, company_name
            FROM clients
            WHERE company_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
              AND (
                  COALESCE(full_name, '') ILIKE %s
                  OR COALESCE(company_name, '') ILIKE %s
                  OR (
                      %s <> ''
                      AND regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g') LIKE %s
                  )
              )
            ORDER BY full_name, id
            LIMIT 11
            """,
            (company_id, f"%{query}%", f"%{query}%", digits, f"%{digits}%"),
        )
        candidates = [dict(row) for row in cur.fetchall()]

        normalized_query = query.casefold()
        query_words = [part for part in normalized_query.split() if part]
        exact = [
            client for client in candidates
            if (
                bool(digits)
                and _normalized_phone(client.get("phone")) == digits
            )
            or str(client.get("company_name") or "").strip().casefold() == normalized_query
            or (
                len(query_words) >= 2
                and str(client.get("full_name") or "").strip().casefold() == normalized_query
            )
        ]
        matches = exact or candidates

        if not matches:
            raise ActionError(f"Клиент «{query}» не найден")
        if len(matches) > 1:
            choices = []
            for client in matches[:5]:
                phone = _normalized_phone(client.get("phone"))
                suffix = f", номер …{phone[-4:]}" if len(phone) >= 4 else ", номер не указан"
                choices.append(f"{client.get('full_name') or 'Без имени'}{suffix}")
            raise ActionError(
                "Найдено несколько клиентов: " + "; ".join(choices)
                + ". Уточните фамилию или последние цифры номера"
            )

        client = matches[0]
        if int(client["id"]) != int(expected_client_id):
            raise ActionError("Выбранный клиент не совпадает с указанным получателем")

        phone = _normalized_phone(client.get("phone"))
        if not 10 <= len(phone) <= 15:
            raise ActionError(
                f"У клиента «{client.get('full_name') or query}» не указан корректный номер WhatsApp"
            )

        cur.execute(
            """
            SELECT id
            FROM whatsapp_integrations
            WHERE company_id = %s
              AND enabled = TRUE
              AND COALESCE(outgoing_enabled, TRUE) = TRUE
            LIMIT 1
            """,
            (company_id,),
        )
        if not cur.fetchone():
            raise ActionError("WhatsApp не подключён или исходящие сообщения отключены")

        client["normalized_phone"] = phone
        return client
    finally:
        cur.close()
        pool.putconn(conn)


def _validate_target(action: str, data: dict[str, Any]) -> dict[str, Any]:
    """Проверяет аргументы и возвращает нормализованную копию без записи в БД."""
    _require_action_access(action)
    normalized = dict(data or {})

    id_actions = {
        "update_client": "client_id",
        "archive_client": "client_id",
        "restore_client": "client_id",
        "delete_client_permanently": "client_id",
        "send_client_whatsapp": "client_id",
        "update_item": "item_id",
        "delete_item": "item_id",
        "update_category": "category_id",
        "delete_category": "category_id",
        "update_task": "task_id",
        "change_task_status": "task_id",
        "delete_task": "task_id",
        "update_expense": "expense_id",
        "delete_expense": "expense_id",
        "update_accounting_document": "document_id",
        "archive_accounting_document": "document_id",
        "delete_accounting_document": "document_id",
        "mark_tax_event_paid": "event_id",
        "delete_tax_event": "event_id",
        "mark_debt_paid": "debt_id",
        "delete_debt": "debt_id",
        "update_user": "target_user_id",
        "delete_user": "target_user_id",
        "update_company": "company_id",
        "delete_company": "company_id",
        "activate_company": "company_id",
    }
    if action in id_actions:
        normalized[id_actions[action]] = _integer(normalized, id_actions[action])

    if action == "create_client":
        normalized["full_name"] = _text(normalized, "full_name", required=True, limit=180)
    elif action == "update_client":
        updates = _allowed_fields(normalized, {
            "full_name", "phone", "iin", "company_name", "status", "category",
            "payment", "comment", "address", "contract_number", "contract_date",
        })
        if not updates:
            raise ActionError("Не указано, что изменить у клиента")
        if "full_name" in updates and not str(updates["full_name"] or "").strip():
            raise ActionError("Имя клиента не может быть пустым")
    elif action == "send_client_whatsapp":
        normalized["recipient_query"] = _text(
            normalized, "recipient_query", required=True, limit=180
        )
        normalized["message"] = _text(normalized, "message", required=True, limit=4000)
        client = _resolve_message_recipient(
            _company_id(), normalized["recipient_query"], normalized["client_id"]
        )
        normalized["client_name"] = str(client.get("full_name") or "Клиент")[:180]
        normalized["client_phone"] = client["normalized_phone"]
    elif action == "create_item":
        normalized["name"] = _text(normalized, "name", required=True, limit=220)
        item_type = _text(normalized, "item_type", limit=20) or "product"
        if item_type not in {"product", "service"}:
            raise ActionError("Тип позиции должен быть product или service")
        normalized["item_type"] = item_type
    elif action == "update_item":
        updates = _allowed_fields(normalized, {
            "name", "category", "unit", "description", "retail_price",
            "wholesale_price", "purchase_price", "discount_percent", "barcode",
            "gtin", "ntin", "is_marked", "item_type", "service_sale_mode",
        })
        if not updates:
            raise ActionError("Не указано, что изменить у товара")
    elif action in {"create_category", "update_category"}:
        normalized["name"] = _text(normalized, "name", required=True, limit=160)
        category_type = _text(normalized, "category_type", limit=20) or "product"
        if category_type not in {"product", "service"}:
            raise ActionError("Тип категории должен быть product или service")
        normalized["category_type"] = category_type
    elif action in {"stock_income", "stock_writeoff"}:
        normalized["item_id"] = _integer(normalized, "item_id")
        normalized["quantity"] = str(_number(normalized, "quantity", minimum=Decimal("0.001")))
        if action == "stock_income":
            normalized["price"] = str(_number(normalized, "price", minimum=Decimal("0")))
    elif action == "create_task":
        normalized["title"] = _text(normalized, "title", required=True, limit=220)
        priority = _text(normalized, "priority", limit=20) or "medium"
        if priority not in TASK_PRIORITIES:
            raise ActionError("Неизвестный приоритет задачи")
        normalized["priority"] = priority
    elif action == "update_task":
        updates = _allowed_fields(normalized, {
            "title", "description", "priority", "status", "assigned_user_id", "due_date",
        })
        if not updates:
            raise ActionError("Не указано, что изменить в задаче")
    elif action == "change_task_status":
        status = _text(normalized, "status", required=True, limit=20)
        if status not in TASK_STATUSES:
            raise ActionError("Неизвестный статус задачи")
        normalized["status"] = status
    elif action in {"create_expense", "update_expense"}:
        if action == "create_expense":
            normalized["description"] = _text(normalized, "description", required=True, limit=160)
        category = _text(normalized, "category", required=action == "create_expense", limit=80)
        if category and category not in EXPENSE_CATEGORIES:
            raise ActionError("Неизвестная категория расхода")
        payment = _text(normalized, "payment_method", required=action == "create_expense", limit=40)
        if payment and payment not in PAYMENT_METHODS:
            raise ActionError("Неизвестный способ оплаты")
        if "amount" in normalized or action == "create_expense":
            normalized["amount"] = str(_number(normalized, "amount", minimum=Decimal("0.01")))
        if "date" in normalized or action == "create_expense":
            normalized["date"] = _date(normalized, "date").isoformat()
    elif action in {"create_accounting_document", "update_accounting_document"}:
        if action == "create_accounting_document":
            normalized["title"] = _text(normalized, "title", required=True, limit=220)
        doc_type = _text(normalized, "document_type", required=action == "create_accounting_document", limit=40)
        if doc_type and doc_type not in DOCUMENT_TYPES:
            raise ActionError("Неизвестный тип бухгалтерского документа")
        if "document_date" in normalized or action == "create_accounting_document":
            normalized["document_date"] = _date(normalized, "document_date").isoformat()
        if "amount" in normalized and normalized.get("amount") not in (None, ""):
            normalized["amount"] = str(_number(normalized, "amount", minimum=Decimal("0")))
    elif action in {"create_tax_event", "create_debt"}:
        normalized["title"] = _text(normalized, "title", required=True, limit=220)
        normalized["due_date"] = _date(normalized, "due_date").isoformat()
        if "amount" in normalized and normalized.get("amount") not in (None, ""):
            normalized["amount"] = str(_number(
                normalized,
                "amount",
                minimum=Decimal("0.01") if action == "create_debt" else Decimal("0"),
            ))
        elif action == "create_debt":
            raise ActionError("Укажите сумму задолженности")
    elif action == "create_user":
        normalized["username"] = _text(normalized, "username", required=True, limit=100)
        normalized["password"] = _text(normalized, "password", required=True, limit=200)
        role = _text(normalized, "role", limit=20) or "employee"
        if role not in USER_ROLES:
            raise ActionError("Неизвестная роль пользователя")
        if not _is_super_admin() and role == "owner":
            raise PermissionDenied("В компании может быть только один владелец")
        if bool(normalized.get("is_super_admin")) and not _is_root_admin():
            raise PermissionDenied("Только главная учётная запись admin назначает супер-администраторов")
        normalized["role"] = role
    elif action == "update_user":
        updates = _allowed_fields(normalized, {
            "username", "password", "role", "position", "full_name", "phone",
            "percent_rate", "module_codes", "company_id", "is_super_admin",
        })
        if not updates:
            raise ActionError("Не указано, что изменить у пользователя")
    elif action == "create_company":
        normalized["name"] = _text(normalized, "name", required=True, limit=220)
    elif action == "update_company":
        updates = _allowed_fields(normalized, {
            "name", "bin", "address", "phone", "iik", "bik", "bank",
            "kbe", "knp", "director", "city", "business_type",
        })
        if not updates:
            raise ActionError("Не указано, что изменить в организации")
    elif action == "create_sale_draft":
        normalized["client_id"] = _integer(normalized, "client_id")
        items = normalized.get("items")
        if not isinstance(items, list) or not items:
            raise ActionError("Добавьте хотя бы одну позицию в продажу")
        clean_items = []
        for item in items[:50]:
            if not isinstance(item, dict):
                raise ActionError("Некорректная позиция продажи")
            clean_items.append({
                "item_id": _integer(item, "item_id"),
                "quantity": str(_number(item, "quantity", minimum=Decimal("0.001"))),
                "price": None if item.get("price") in (None, "") else str(
                    _number(item, "price", minimum=Decimal("0"))
                ),
            })
        normalized["items"] = clean_items

    return normalized


def _subject_label(action: str, data: dict[str, Any]) -> str:
    labels = {
        "create_client": f"создать клиента «{data.get('full_name', '')}»",
        "update_client": f"изменить клиента #{data.get('client_id')}",
        "archive_client": f"переместить клиента #{data.get('client_id')} в удалённые",
        "restore_client": f"восстановить клиента #{data.get('client_id')}",
        "delete_client_permanently": f"безвозвратно удалить клиента #{data.get('client_id')}",
        "send_client_whatsapp": (
            f"отправить WhatsApp клиенту «{data.get('client_name', 'Клиент')}» "
            f"({data.get('client_phone', '')}):\n"
            f"{str(data.get('message') or '')[:650]}"
            + ("…" if len(str(data.get('message') or '')) > 650 else "")
        ),
        "create_item": f"создать позицию «{data.get('name', '')}»",
        "update_item": f"изменить позицию #{data.get('item_id')}",
        "delete_item": f"удалить позицию #{data.get('item_id')}",
        "create_category": f"создать категорию «{data.get('name', '')}»",
        "update_category": f"изменить категорию #{data.get('category_id')}",
        "delete_category": f"удалить категорию #{data.get('category_id')}",
        "stock_income": f"оформить приход {data.get('quantity')} ед. товара #{data.get('item_id')}",
        "stock_writeoff": f"списать {data.get('quantity')} ед. товара #{data.get('item_id')}",
        "create_task": f"создать задачу «{data.get('title', '')}»",
        "update_task": f"изменить задачу #{data.get('task_id')}",
        "change_task_status": f"сменить статус задачи #{data.get('task_id')} на {data.get('status')}",
        "delete_task": f"удалить задачу #{data.get('task_id')}",
        "create_expense": f"создать расход «{data.get('description', '')}» на {data.get('amount')} тенге",
        "update_expense": f"изменить расход #{data.get('expense_id')}",
        "delete_expense": f"удалить расход #{data.get('expense_id')}",
        "create_accounting_document": f"создать документ «{data.get('title', '')}»",
        "update_accounting_document": f"изменить документ #{data.get('document_id')}",
        "archive_accounting_document": f"архивировать документ #{data.get('document_id')}",
        "delete_accounting_document": f"удалить документ #{data.get('document_id')}",
        "create_tax_event": f"создать налоговое событие «{data.get('title', '')}»",
        "mark_tax_event_paid": f"отметить налоговое событие #{data.get('event_id')} оплаченным",
        "delete_tax_event": f"удалить налоговое событие #{data.get('event_id')}",
        "create_debt": f"создать задолженность «{data.get('title', '')}»",
        "mark_debt_paid": f"отметить задолженность #{data.get('debt_id')} оплаченной",
        "delete_debt": f"удалить задолженность #{data.get('debt_id')}",
        "create_user": f"создать пользователя «{data.get('username', '')}»",
        "update_user": f"изменить пользователя #{data.get('target_user_id')}",
        "delete_user": f"удалить пользователя #{data.get('target_user_id')}",
        "create_company": f"создать организацию «{data.get('name', '')}»",
        "update_company": f"изменить организацию #{data.get('company_id')}",
        "delete_company": f"удалить организацию #{data.get('company_id')}",
        "activate_company": f"сделать организацию #{data.get('company_id')} активной",
        "create_sale_draft": f"создать черновик продажи клиенту #{data.get('client_id')}",
    }
    return labels.get(action, action)


def prepare_action(action: str, data: dict[str, Any]) -> dict[str, Any]:
    normalized = _validate_target(action, data)
    return {
        "action": action,
        "arguments": normalized,
        "summary": _subject_label(action, normalized),
    }


def _update_fields(cur, table: str, record_id: int, company_id: int, updates: dict[str, Any]):
    if not updates:
        raise ActionError("Нет данных для изменения")
    clauses = []
    params = []
    for key, value in updates.items():
        clauses.append(f"{key} = %s")
        params.append(value)
    params.extend([record_id, company_id])
    cur.execute(
        f"UPDATE {table} SET {', '.join(clauses)} WHERE id = %s AND company_id = %s RETURNING *",
        tuple(params),
    )
    updated = cur.fetchone()
    if not updated:
        raise ActionError("Запись не найдена")
    return dict(updated)


def _set_user_modules(cur, employee_id: int, company_id: int | None, module_codes: list[str]):
    cur.execute("DELETE FROM employee_module_permissions WHERE employee_id = %s", (employee_id,))
    if not company_id:
        return
    clean_codes = {str(code).strip() for code in (module_codes or []) if str(code).strip()}
    cur.execute(
        """
        SELECT m.id, m.code
        FROM modules m
        JOIN company_modules cm ON cm.module_id = m.id
        WHERE cm.company_id = %s AND cm.enabled = TRUE AND m.is_active = TRUE
        """,
        (company_id,),
    )
    for row in cur.fetchall():
        cur.execute(
            """
            INSERT INTO employee_module_permissions (employee_id, module_id, allowed)
            VALUES (%s, %s, %s)
            ON CONFLICT (employee_id, module_id)
            DO UPDATE SET allowed = EXCLUDED.allowed
            """,
            (employee_id, row["id"], row["code"] in clean_codes),
        )


def _execute(cur, action: str, data: dict[str, Any]) -> dict[str, Any]:
    needs_company = action in ACTION_MODULES or (
        action in OWNER_ACTIONS and not _is_super_admin()
    )
    company_id = _company_id(required=needs_company)
    actor_id = _user_id()
    before = None
    after = None
    target_type = action.split("_", 1)[-1]
    target_id = None

    if action == "create_client":
        cur.execute(
            """
            INSERT INTO clients (
                full_name, phone, iin, company_name, status, category, payment,
                comment, address, contract_number, contract_date, created_at,
                company_id, is_deleted
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                NULLIF(%s, '')::date, %s, %s, FALSE
            ) RETURNING *
            """,
            (
                data["full_name"], _text(data, "phone", limit=50), _text(data, "iin", limit=20),
                _text(data, "company_name", limit=220), _text(data, "status", limit=60) or "Новый",
                _text(data, "category", limit=80), _text(data, "payment", limit=60) or "Не оплачено",
                _text(data, "comment", limit=1000), _text(data, "address", limit=500),
                _text(data, "contract_number", limit=100), _text(data, "contract_date", limit=10),
                now_kz(), company_id,
            ),
        )
        after = dict(cur.fetchone())
        target_id = after["id"]

    elif action in {"update_client", "archive_client", "restore_client", "delete_client_permanently"}:
        client_id = data["client_id"]
        before = _row(cur, "SELECT * FROM clients WHERE id = %s AND company_id = %s", (client_id, company_id), "Клиент не найден")
        target_id = client_id
        if action == "update_client":
            updates = _allowed_fields(data, {
                "full_name", "phone", "iin", "company_name", "status", "category",
                "payment", "comment", "address", "contract_number", "contract_date",
            })
            if "contract_date" in updates:
                date_value = str(updates.pop("contract_date") or "").strip()
                clauses = [f"{key} = %s" for key in updates]
                params = list(updates.values())
                clauses.append("contract_date = NULLIF(%s, '')::date")
                params.append(date_value)
                params.extend([client_id, company_id])
                cur.execute(
                    f"UPDATE clients SET {', '.join(clauses)} WHERE id = %s AND company_id = %s RETURNING *",
                    tuple(params),
                )
                after = dict(cur.fetchone())
            else:
                after = _update_fields(cur, "clients", client_id, company_id, updates)
        elif action == "archive_client":
            cur.execute("UPDATE clients SET is_deleted = TRUE WHERE id = %s AND company_id = %s RETURNING *", (client_id, company_id))
            after = dict(cur.fetchone())
        elif action == "restore_client":
            cur.execute("UPDATE clients SET is_deleted = FALSE WHERE id = %s AND company_id = %s RETURNING *", (client_id, company_id))
            after = dict(cur.fetchone())
        else:
            if not before.get("is_deleted"):
                raise ActionError("Сначала переместите клиента в удалённые")
            cur.execute("DELETE FROM clients WHERE id = %s AND company_id = %s RETURNING id", (client_id, company_id))

    elif action == "send_client_whatsapp":
        client = _row(
            cur,
            """
            SELECT id, full_name, phone, company_name
            FROM clients
            WHERE id = %s AND company_id = %s AND COALESCE(is_deleted, FALSE) = FALSE
            """,
            (data["client_id"], company_id),
            "Клиент не найден",
        )
        phone = _normalized_phone(client.get("phone"))
        if phone != data.get("client_phone"):
            raise ActionError("Номер клиента изменился. Подготовьте сообщение заново")

        cur.execute(
            """
            SELECT id, instance_id, api_token, phone
            FROM whatsapp_integrations
            WHERE company_id = %s
              AND enabled = TRUE
              AND COALESCE(outgoing_enabled, TRUE) = TRUE
            LIMIT 1
            """,
            (company_id,),
        )
        integration = cur.fetchone()
        if not integration:
            raise ActionError("WhatsApp не подключён или исходящие сообщения отключены")

        external_chat_id = f"{phone}@c.us"
        cur.execute(
            """
            SELECT id, customer_id
            FROM whatsapp_chats
            WHERE company_id = %s AND integration_id = %s AND external_chat_id = %s
            LIMIT 1
            """,
            (company_id, integration["id"], external_chat_id),
        )
        chat = cur.fetchone()
        if chat and chat.get("customer_id") not in (None, client["id"]):
            raise ActionError(
                "Этот WhatsApp-чат уже связан с другой карточкой клиента. Проверьте номер"
            )

        if chat:
            chat_id = chat["id"]
            cur.execute(
                """
                UPDATE whatsapp_chats
                SET phone = %s,
                    contact_name = COALESCE(NULLIF(contact_name, ''), %s),
                    customer_id = COALESCE(customer_id, %s),
                    updated_at = NOW()
                WHERE id = %s AND company_id = %s
                """,
                (phone, client["full_name"], client["id"], chat_id, company_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO whatsapp_chats (
                    company_id, integration_id, external_chat_id, phone,
                    contact_name, customer_id, unread_count, created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,0,NOW(),NOW())
                RETURNING id
                """,
                (
                    company_id, integration["id"], external_chat_id, phone,
                    client["full_name"], client["id"],
                ),
            )
            chat_id = cur.fetchone()["id"]

        try:
            response = requests.post(
                f"https://api.green-api.com/waInstance{integration['instance_id']}/"
                f"sendMessage/{integration['api_token']}",
                json={"chatId": external_chat_id, "message": data["message"]},
                timeout=25,
            )
            response.raise_for_status()
            external_message_id = response.json().get("idMessage")
            if not external_message_id:
                raise requests.RequestException("GREEN-API returned no message id")
        except (requests.RequestException, ValueError) as error:
            raise ActionError("Не удалось отправить сообщение через WhatsApp") from error

        cur.execute(
            """
            INSERT INTO whatsapp_messages (
                company_id, integration_id, chat_id, external_message_id,
                direction, message_type, message_text, sender_phone,
                status, is_ai, created_at
            )
            VALUES (%s,%s,%s,%s,'outgoing','textMessage',%s,%s,'sent',TRUE,NOW())
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                company_id, integration["id"], chat_id, external_message_id,
                data["message"], integration.get("phone") or "",
            ),
        )
        saved_message = cur.fetchone()
        if saved_message:
            target_id = saved_message["id"]
        else:
            cur.execute(
                """
                SELECT id FROM whatsapp_messages
                WHERE integration_id = %s AND external_message_id = %s
                LIMIT 1
                """,
                (integration["id"], external_message_id),
            )
            target_id = cur.fetchone()["id"]

        cur.execute(
            """
            UPDATE whatsapp_chats
            SET last_message = %s, last_message_at = NOW(), updated_at = NOW()
            WHERE id = %s AND company_id = %s
            """,
            (data["message"], chat_id, company_id),
        )
        target_type = "whatsapp_message"
        before = {
            "client_id": client["id"],
            "client_name": client["full_name"],
            "phone": phone,
        }
        after = {
            **before,
            "chat_id": chat_id,
            "external_message_id": external_message_id,
            "message": data["message"],
            "status": "sent",
        }

    elif action == "create_item":
        item_type = data.get("item_type") or "product"
        cur.execute(
            """
            INSERT INTO items (
                name, category, unit, description, retail_price, wholesale_price,
                purchase_price, discount_percent, barcode, gtin, ntin, is_marked,
                item_type, service_sale_mode, company_id
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                data["name"], _text(data, "category", limit=160), _text(data, "unit", limit=40),
                _text(data, "description", limit=2000), _number(data, "retail_price", required=False) or 0,
                _number(data, "wholesale_price", required=False) or 0,
                _number(data, "purchase_price", required=False) or 0,
                int(data.get("discount_percent") or 0), _text(data, "barcode", limit=100),
                _text(data, "gtin", limit=100), _text(data, "ntin", limit=100) if item_type == "product" else "",
                bool(data.get("is_marked")) if item_type == "product" else False,
                item_type, (_text(data, "service_sale_mode", limit=30) or "order") if item_type == "service" else None,
                company_id,
            ),
        )
        after = dict(cur.fetchone())
        target_id = after["id"]

    elif action in {"update_item", "delete_item"}:
        item_id = data["item_id"]
        before = _row(cur, "SELECT * FROM items WHERE id = %s AND company_id = %s", (item_id, company_id), "Позиция не найдена")
        target_id = item_id
        if action == "update_item":
            updates = _allowed_fields(data, {
                "name", "category", "unit", "description", "retail_price", "wholesale_price",
                "purchase_price", "discount_percent", "barcode", "gtin", "ntin", "is_marked",
                "item_type", "service_sale_mode",
            })
            after = _update_fields(cur, "items", item_id, company_id, updates)
        else:
            cur.execute("DELETE FROM items WHERE id = %s AND company_id = %s RETURNING id", (item_id, company_id))

    elif action in {"create_category", "update_category", "delete_category"}:
        if action == "create_category":
            markup = _number(data, "markup_percent", required=False) or 0
            if data["category_type"] == "service":
                markup = 0
            cur.execute(
                "INSERT INTO categories (company_id, name, markup_percent, category_type) VALUES (%s,%s,%s,%s) RETURNING *",
                (company_id, data["name"], markup, data["category_type"]),
            )
            after = dict(cur.fetchone())
            target_id = after["id"]
        else:
            category_id = data["category_id"]
            before = _row(cur, "SELECT * FROM categories WHERE id = %s AND company_id = %s", (category_id, company_id), "Категория не найдена")
            target_id = category_id
            if action == "update_category":
                markup = _number(data, "markup_percent", required=False) or 0
                if data["category_type"] == "service":
                    markup = 0
                cur.execute(
                    "UPDATE categories SET name=%s, markup_percent=%s, category_type=%s WHERE id=%s AND company_id=%s RETURNING *",
                    (data["name"], markup, data["category_type"], category_id, company_id),
                )
                after = dict(cur.fetchone())
            else:
                cur.execute("DELETE FROM categories WHERE id=%s AND company_id=%s RETURNING id", (category_id, company_id))

    elif action in {"stock_income", "stock_writeoff"}:
        item_id = data["item_id"]
        item = _row(
            cur,
            "SELECT id, name, purchase_price, item_type FROM items WHERE id=%s AND company_id=%s",
            (item_id, company_id),
            "Товар не найден",
        )
        if (item.get("item_type") or "product") != "product":
            raise ActionError("Складские операции доступны только для товаров")
        quantity = Decimal(data["quantity"])
        movement_type = "income" if action == "stock_income" else "writeoff"
        if action == "stock_writeoff":
            cur.execute(
                """
                SELECT COALESCE(SUM(CASE WHEN movement_type IN ('income','refund') THEN quantity WHEN movement_type IN ('sale','writeoff') THEN -quantity ELSE 0 END),0) AS stock
                FROM stock_movements WHERE company_id=%s AND item_id=%s
                """,
                (company_id, item_id),
            )
            stock = Decimal(str(cur.fetchone()["stock"] or 0))
            if quantity > stock:
                raise ActionError(f"Недостаточно товара. Доступно {stock}")
            price = Decimal(str(item.get("purchase_price") or 0))
        else:
            price = Decimal(data["price"])
        total = quantity * price
        cur.execute(
            """
            INSERT INTO stock_movements (company_id,item_id,movement_type,quantity,price,total,comment,created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (company_id, item_id, movement_type, quantity, price, total, _text(data, "comment", limit=500), now_kz()),
        )
        after = dict(cur.fetchone())
        target_id = after["id"]
        target_type = "stock_movement"
        if action == "stock_income":
            from routes.expenses import upsert_expense_from_source, _sync_expense_to_accounting
            expense_id = upsert_expense_from_source(
                cur,
                company_id=company_id,
                source_type="stock_income",
                source_id=target_id,
                category="Закупки",
                description=f"Закуп товара: {item['name']}",
                amount=total,
                expense_date=now_kz().date(),
                payment_method=data.get("payment_method") or "Другое",
                comment=_text(data, "comment", limit=500) or "Создано Nika AI из прихода товара",
                user_id=actor_id,
            )
            _sync_expense_to_accounting(cur, expense_id, company_id)
            after["expense_id"] = expense_id

    elif action in {"create_task", "update_task", "change_task_status", "delete_task"}:
        if action == "create_task":
            assigned = _integer(data, "assigned_user_id", required=False)
            if assigned:
                _row(cur, "SELECT id FROM users WHERE id=%s AND company_id=%s", (assigned, company_id), "Сотрудник для задачи не найден")
            due = _date(data, "due_date", required=False)
            cur.execute(
                """
                INSERT INTO tasks (company_id,created_by,assigned_user_id,title,description,priority,status,due_date,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,'new',%s,%s) RETURNING *
                """,
                (company_id, actor_id, assigned, data["title"], _text(data, "description", limit=2000) or None, data["priority"], due.isoformat() if due else None, now_kz()),
            )
            after = dict(cur.fetchone())
            target_id = after["id"]
        else:
            task_id = data["task_id"]
            before = _row(cur, "SELECT * FROM tasks WHERE id=%s AND company_id=%s", (task_id, company_id), "Задача не найдена")
            target_id = task_id
            if action == "delete_task":
                cur.execute("DELETE FROM tasks WHERE id=%s AND company_id=%s RETURNING id", (task_id, company_id))
            elif action == "change_task_status":
                if _role() == "employee" and before.get("assigned_user_id") != actor_id:
                    raise PermissionDenied("Сотрудник может менять статус только своей задачи")
                completed_at = now_kz() if data["status"] == "done" else None
                cur.execute(
                    "UPDATE tasks SET status=%s, completed_at=%s, updated_at=%s WHERE id=%s AND company_id=%s RETURNING *",
                    (data["status"], completed_at, now_kz(), task_id, company_id),
                )
                after = dict(cur.fetchone())
            else:
                updates = _allowed_fields(data, {"title", "description", "priority", "status", "assigned_user_id", "due_date"})
                if "priority" in updates and updates["priority"] not in TASK_PRIORITIES:
                    raise ActionError("Неизвестный приоритет")
                if "status" in updates and updates["status"] not in TASK_STATUSES:
                    raise ActionError("Неизвестный статус")
                if "due_date" in updates:
                    updates["due_date"] = _date(updates, "due_date", required=False)
                updates["updated_at"] = now_kz()
                after = _update_fields(cur, "tasks", task_id, company_id, updates)

    elif action in {"create_expense", "update_expense", "delete_expense"}:
        if action == "create_expense":
            cur.execute(
                """
                INSERT INTO expenses (company_id,user_id,category,description,amount,payment_method,comment,date,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (company_id, actor_id, data["category"], data["description"], Decimal(data["amount"]), data["payment_method"], _text(data, "comment", limit=500), _date(data, "date"), now_kz()),
            )
            after = dict(cur.fetchone())
            target_id = after["id"]
            from routes.expenses import _sync_expense_to_accounting
            _sync_expense_to_accounting(cur, target_id, company_id)
        else:
            expense_id = data["expense_id"]
            before = _row(cur, "SELECT * FROM expenses WHERE id=%s AND company_id=%s", (expense_id, company_id), "Расход не найден")
            if before.get("source_type"):
                raise ActionError("Автоматический расход изменяется в исходном разделе")
            target_id = expense_id
            if action == "delete_expense":
                cur.execute("DELETE FROM expenses WHERE id=%s AND company_id=%s RETURNING id", (expense_id, company_id))
                from routes.expenses import _delete_expense_from_accounting
                _delete_expense_from_accounting(cur, expense_id, company_id)
            else:
                updates = _allowed_fields(data, {"category", "description", "amount", "payment_method", "comment", "date"})
                if "amount" in updates:
                    updates["amount"] = Decimal(str(updates["amount"]))
                if "date" in updates:
                    updates["date"] = _date(updates, "date")
                updates["updated_at"] = now_kz()
                after = _update_fields(cur, "expenses", expense_id, company_id, updates)
                from routes.expenses import _sync_expense_to_accounting
                _sync_expense_to_accounting(cur, expense_id, company_id)

    elif action in {
        "create_accounting_document", "update_accounting_document", "archive_accounting_document",
        "delete_accounting_document", "create_tax_event", "mark_tax_event_paid", "delete_tax_event",
        "create_debt", "mark_debt_paid", "delete_debt",
    }:
        from routes.accounting import _ensure_accounting_tables
        _ensure_accounting_tables(cur)
        if action == "create_accounting_document":
            cur.execute(
                """
                INSERT INTO accounting_documents (company_id,user_id,title,document_type,document_number,document_date,amount,counterparty,comment,status,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s) RETURNING *
                """,
                (company_id, actor_id, data["title"], data["document_type"], _text(data, "document_number", limit=100) or None, _date(data, "document_date"), Decimal(data["amount"]) if data.get("amount") else None, _text(data, "counterparty", limit=220) or None, _text(data, "comment", limit=1000) or None, now_kz()),
            )
            after = dict(cur.fetchone()); target_id = after["id"]; target_type = "accounting_document"
        elif action in {"update_accounting_document", "archive_accounting_document", "delete_accounting_document"}:
            document_id = data["document_id"]
            before = _row(cur, "SELECT * FROM accounting_documents WHERE id=%s AND company_id=%s", (document_id, company_id), "Документ не найден")
            target_id = document_id; target_type = "accounting_document"
            if action == "delete_accounting_document":
                if before.get("stored_filename"):
                    raise ActionError("Документ с прикреплённым файлом удалите в разделе бухгалтерии")
                cur.execute("DELETE FROM accounting_documents WHERE id=%s AND company_id=%s RETURNING id", (document_id, company_id))
            elif action == "archive_accounting_document":
                cur.execute("UPDATE accounting_documents SET status='archived', archived_at=%s, updated_at=%s WHERE id=%s AND company_id=%s RETURNING *", (now_kz(), now_kz(), document_id, company_id))
                after = dict(cur.fetchone())
            else:
                updates = _allowed_fields(data, {"title", "document_type", "document_number", "document_date", "amount", "counterparty", "comment"})
                if "document_date" in updates: updates["document_date"] = _date(updates, "document_date")
                if "amount" in updates and updates["amount"] not in (None, ""): updates["amount"] = Decimal(str(updates["amount"]))
                updates["updated_at"] = now_kz()
                after = _update_fields(cur, "accounting_documents", document_id, company_id, updates)
        elif action == "create_tax_event":
            cur.execute(
                "INSERT INTO accounting_tax_events (company_id,user_id,title,description,due_date,amount,status,created_at) VALUES (%s,%s,%s,%s,%s,%s,'planned',%s) RETURNING *",
                (company_id, actor_id, data["title"], _text(data, "description", limit=1000) or None, _date(data, "due_date"), Decimal(data["amount"]) if data.get("amount") else None, now_kz()),
            )
            after = dict(cur.fetchone()); target_id = after["id"]; target_type = "tax_event"
        elif action in {"mark_tax_event_paid", "delete_tax_event"}:
            event_id = data["event_id"]
            before = _row(cur, "SELECT * FROM accounting_tax_events WHERE id=%s AND company_id=%s", (event_id, company_id), "Налоговое событие не найдено")
            target_id = event_id; target_type = "tax_event"
            if action == "delete_tax_event": cur.execute("DELETE FROM accounting_tax_events WHERE id=%s AND company_id=%s RETURNING id", (event_id, company_id))
            else:
                cur.execute("UPDATE accounting_tax_events SET status='paid', paid_at=%s, updated_at=%s WHERE id=%s AND company_id=%s RETURNING *", (now_kz(), now_kz(), event_id, company_id))
                after = dict(cur.fetchone())
        elif action == "create_debt":
            cur.execute(
                "INSERT INTO accounting_debts (company_id,user_id,title,description,due_date,amount,status,created_at) VALUES (%s,%s,%s,%s,%s,%s,'debt',%s) RETURNING *",
                (company_id, actor_id, data["title"], _text(data, "description", limit=1000) or None, _date(data, "due_date"), Decimal(data["amount"]), now_kz()),
            )
            after = dict(cur.fetchone()); target_id = after["id"]; target_type = "debt"
        else:
            debt_id = data["debt_id"]
            before = _row(cur, "SELECT * FROM accounting_debts WHERE id=%s AND company_id=%s", (debt_id, company_id), "Задолженность не найдена")
            target_id = debt_id; target_type = "debt"
            if action == "delete_debt": cur.execute("DELETE FROM accounting_debts WHERE id=%s AND company_id=%s RETURNING id", (debt_id, company_id))
            else:
                cur.execute("UPDATE accounting_debts SET status='paid', paid_at=%s, updated_at=%s WHERE id=%s AND company_id=%s RETURNING *", (now_kz(), now_kz(), debt_id, company_id))
                after = dict(cur.fetchone())
                from routes.accounting import _create_expense_from_paid_debt
                _create_expense_from_paid_debt(cur, after, company_id)

    elif action in {"create_user", "update_user", "delete_user"}:
        current_company_id = _company_id(required=not _is_super_admin())
        if action == "create_user":
            requested_company_id = int(data.get("company_id") or current_company_id or 0) or None
            role = data["role"]
            requested_super = bool(data.get("is_super_admin"))
            if requested_super and not _is_root_admin():
                raise PermissionDenied("Только главная учётная запись admin назначает супер-администраторов")
            if not _is_super_admin():
                requested_company_id = current_company_id
                requested_super = False
                if role == "owner":
                    raise PermissionDenied("В компании может быть только один владелец")
            if not requested_company_id and not requested_super:
                raise ActionError("Для пользователя выберите организацию")
            cur.execute("SELECT id FROM users WHERE username=%s", (data["username"],))
            if cur.fetchone(): raise ActionError("Пользователь с таким логином уже существует")
            cur.execute(
                """
                INSERT INTO users (username,password,role,position,company_id,full_name,phone,percent_rate,is_super_admin,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (data["username"], data["password"], role, _text(data, "position", limit=120), requested_company_id, _text(data, "full_name", limit=180), _text(data, "phone", limit=50), _number(data, "percent_rate", required=False) or 0, requested_super, now_kz()),
            )
            after = dict(cur.fetchone()); target_id = after["id"]; target_type = "user"
            if not requested_super and role == "employee":
                _set_user_modules(cur, target_id, requested_company_id, data.get("module_codes") or [])
        else:
            target_user_id = data["target_user_id"]
            before = _row(cur, "SELECT * FROM users WHERE id=%s", (target_user_id,), "Пользователь не найден")
            target_id = target_user_id; target_type = "user"
            if target_user_id == actor_id and action == "delete_user":
                raise PermissionDenied("Нельзя удалить самого себя")
            if not _is_super_admin() and before.get("company_id") != current_company_id:
                raise PermissionDenied("Нельзя управлять пользователем другой организации")
            if before.get("is_super_admin") and not (_is_root_admin() or target_user_id == actor_id):
                raise PermissionDenied("Только главная учётная запись admin управляет другими супер-администраторами")
            if before.get("role") == "owner" and not _is_super_admin() and target_user_id != actor_id:
                raise PermissionDenied("Владельца может изменить только супер-администратор")
            if action == "delete_user":
                cur.execute("DELETE FROM employee_module_permissions WHERE employee_id=%s", (target_user_id,))
                cur.execute("DELETE FROM users WHERE id=%s RETURNING id", (target_user_id,))
            else:
                updates = _allowed_fields(data, {"username", "password", "role", "position", "full_name", "phone", "percent_rate", "company_id", "is_super_admin"})
                if "role" in updates and updates["role"] not in USER_ROLES: raise ActionError("Неизвестная роль")
                if "username" in updates:
                    username = str(updates["username"] or "").strip()
                    if not username:
                        raise ActionError("Логин не может быть пустым")
                    cur.execute("SELECT id FROM users WHERE username=%s AND id<>%s", (username, target_user_id))
                    if cur.fetchone():
                        raise ActionError("Пользователь с таким логином уже существует")
                    updates["username"] = username
                if not _is_super_admin():
                    updates.pop("company_id", None); updates.pop("is_super_admin", None)
                    if updates.get("role") == "owner": raise PermissionDenied("Нельзя назначить второго владельца")
                if "is_super_admin" in updates and bool(updates["is_super_admin"]) != bool(before.get("is_super_admin")) and not _is_root_admin():
                    raise PermissionDenied("Только главная учётная запись admin меняет статус супер-администратора")
                if target_user_id == actor_id and _is_root_admin():
                    updates["username"] = "admin"
                    updates["is_super_admin"] = True
                    updates["company_id"] = None
                projected_super = bool(updates.get("is_super_admin", before.get("is_super_admin")))
                projected_company = updates.get("company_id", before.get("company_id"))
                if not projected_super and not projected_company:
                    raise ActionError("Для пользователя необходимо выбрать организацию")
                after = _update_fields(cur, "users", target_user_id, int(before.get("company_id") or current_company_id or 0), updates) if before.get("company_id") else None
                if before.get("company_id") is None:
                    clauses = [f"{key}=%s" for key in updates]; params = list(updates.values()) + [target_user_id]
                    cur.execute(f"UPDATE users SET {', '.join(clauses)} WHERE id=%s RETURNING *", tuple(params)); after = dict(cur.fetchone())
                if "module_codes" in data and not after.get("is_super_admin") and after.get("role") == "employee":
                    _set_user_modules(cur, target_user_id, after.get("company_id"), data.get("module_codes") or [])

    elif action in SUPER_ADMIN_ACTIONS:
        if action == "create_company":
            cur.execute(
                """
                INSERT INTO companies (name,bin,address,phone,iik,bik,bank,kbe,knp,director,city,business_type,created_at,is_active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE) RETURNING *
                """,
                (data["name"], _text(data,"bin",limit=20), _text(data,"address",limit=500), _text(data,"phone",limit=50), _text(data,"iik",limit=60), _text(data,"bik",limit=30), _text(data,"bank",limit=180), _text(data,"kbe",limit=10), _text(data,"knp",limit=10), _text(data,"director",limit=180), _text(data,"city",limit=120), _text(data,"business_type",limit=120), now_kz()),
            )
            after = dict(cur.fetchone()); target_id = after["id"]; target_type = "company"
            cur.execute(
                """
                INSERT INTO company_subscriptions (company_id,status,billing_period,base_price,trial_ends_at,period_start,next_payment_at)
                VALUES (%s,'trial','month',2990,NOW()+INTERVAL '14 days',NOW(),NOW()+INTERVAL '14 days')
                ON CONFLICT (company_id) DO NOTHING
                """, (target_id,),
            )
            cur.execute(
                """
                INSERT INTO company_modules (company_id,module_id,enabled,status,price,billing_period)
                SELECT %s,id,TRUE,'trial',monthly_price,'month' FROM modules
                WHERE is_active=TRUE AND (is_core=TRUE OR code IN ('sales','catalog','warehouse','clients','analytics'))
                ON CONFLICT (company_id,module_id) DO NOTHING
                """, (target_id,),
            )
        else:
            target_company_id = data["company_id"]
            before = _row(cur, "SELECT * FROM companies WHERE id=%s", (target_company_id,), "Организация не найдена")
            target_id = target_company_id; target_type = "company"
            if action == "update_company":
                updates = _allowed_fields(data, {"name","bin","address","phone","iik","bik","bank","kbe","knp","director","city","business_type"})
                clauses = [f"{key}=%s" for key in updates]; params = list(updates.values()) + [target_company_id]
                cur.execute(f"UPDATE companies SET {', '.join(clauses)} WHERE id=%s RETURNING *", tuple(params)); after = dict(cur.fetchone())
            elif action == "activate_company":
                cur.execute("UPDATE companies SET is_active=FALSE")
                cur.execute("UPDATE companies SET is_active=TRUE WHERE id=%s RETURNING *", (target_company_id,)); after = dict(cur.fetchone())
            else:
                cur.execute("SELECT COUNT(*) AS count FROM users WHERE company_id=%s", (target_company_id,))
                if int(cur.fetchone()["count"] or 0) > 0: raise ActionError("Сначала удалите или перенесите пользователей организации")
                for table_name in ("items", "clients", "sales", "stock_movements", "tasks", "expenses"):
                    cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table_name}",))
                    if not cur.fetchone()["table_name"]:
                        continue
                    cur.execute(f"SELECT COUNT(*) AS count FROM {table_name} WHERE company_id=%s", (target_company_id,))
                    if int(cur.fetchone()["count"] or 0) > 0:
                        raise ActionError("Организация содержит рабочие данные и не может быть удалена")
                for child_table in (
                    "employee_module_permissions", "company_modules", "company_subscriptions",
                    "subscription_payments", "subscription_changes", "onboarding_progress",
                ):
                    cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{child_table}",))
                    if not cur.fetchone()["table_name"]:
                        continue
                    if child_table == "employee_module_permissions":
                        continue
                    cur.execute(f"DELETE FROM {child_table} WHERE company_id=%s", (target_company_id,))
                cur.execute("DELETE FROM companies WHERE id=%s RETURNING id", (target_company_id,))

    elif action == "create_sale_draft":
        client = _row(cur, "SELECT id,full_name FROM clients WHERE id=%s AND company_id=%s AND COALESCE(is_deleted,FALSE)=FALSE", (data["client_id"], company_id), "Клиент не найден")
        sale_lines = []
        total = Decimal("0")
        for line in data["items"]:
            item = _row(cur, "SELECT id,name,unit,retail_price FROM items WHERE id=%s AND company_id=%s", (line["item_id"], company_id), "Позиция продажи не найдена")
            quantity = Decimal(line["quantity"]); price = Decimal(line["price"]) if line.get("price") else Decimal(str(item.get("retail_price") or 0))
            line_total = quantity * price; total += line_total
            sale_lines.append((item, quantity, price, line_total))
        cur.execute("SELECT COALESCE(MAX(sale_number),0)+1 AS next_number FROM sales WHERE company_id=%s", (company_id,))
        sale_number = cur.fetchone()["next_number"]
        cur.execute(
            """
            INSERT INTO sales (client_id,company_id,sale_number,total_amount,paid_amount,status,created_at,sale_type,user_id)
            VALUES (%s,%s,%s,%s,0,'Новая',%s,'ai_draft',%s) RETURNING *
            """,
            (client["id"], company_id, sale_number, total, now_kz(), actor_id),
        )
        after = dict(cur.fetchone()); target_id = after["id"]; target_type = "sale"
        for item, quantity, price, line_total in sale_lines:
            cur.execute(
                "INSERT INTO sale_items (sale_id,item_id,name,price,quantity,total,unit) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (target_id, item["id"], item["name"], price, quantity, line_total, item.get("unit") or "шт"),
            )
        after["client_name"] = client["full_name"]

    result_message = (
        f"Сообщение клиенту «{data.get('client_name', 'Клиент')}» отправлено."
        if action == "send_client_whatsapp"
        else f"Готово: {_subject_label(action, data)}."
    )
    return {
        "message": result_message,
        "target_type": target_type,
        "target_id": target_id,
        "before": _clean_dict(before),
        "after": _clean_dict(after),
    }


def execute_action(action: str, data: dict[str, Any]) -> dict[str, Any]:
    normalized = _validate_target(action, data)
    conn = get_db()
    cur = conn.cursor()
    try:
        result = _execute(cur, action, normalized)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)
