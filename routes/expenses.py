from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from math import ceil

from flask import Blueprint, redirect, render_template, request, session

from models import get_db, pool
from utils.timezone import now_kz


expenses_bp = Blueprint("expenses", __name__)

EXPENSE_CATEGORIES = [
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
]

AUTOMATIC_SOURCE_TYPES = {
    "stock_income",
    "salary",
    "tax",
    "bank_commission",
    "delivery",
}

PAYMENT_METHODS = {
    "Наличные",
    "Банковская карта",
    "Kaspi",
    "Расчётный счёт",
    "Другое",
}

PER_PAGE = 25


@dataclass
class Pagination:
    page: int
    per_page: int
    total: int

    @property
    def pages(self):
        return max(1, ceil(self.total / self.per_page))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1

    @property
    def next_num(self):
        return self.page + 1


def _require_company():
    """Возвращает company_id или None, если пользователь не авторизован."""
    if not session.get("user_id"):
        return None

    return session.get("company_id")


def _ensure_expenses_table(cur):
    """Создаёт таблицу расходов при первом запуске модуля."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
            payment_method TEXT,
            comment TEXT,
            date DATE NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_expenses_company_date
        ON expenses (company_id, date DESC, id DESC)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_expenses_company_category
        ON expenses (company_id, category)
    """)

    # Связь с исходными документами: налогами, зарплатой и другими модулями.
    cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS source_type TEXT")
    cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS source_id INTEGER")

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_expenses_source
        ON expenses(company_id, source_type, source_id)
        WHERE source_type IS NOT NULL AND source_id IS NOT NULL
    """)



def _ensure_accounting_operations_table(cur):
    """Минимальная таблица для мгновенной связи расходов с бухгалтерией."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounting_operations (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            operation_type TEXT NOT NULL,
            title TEXT NOT NULL,
            amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            payment_method TEXT,
            counterparty TEXT,
            operation_date DATE NOT NULL,
            document_url TEXT,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP,
            UNIQUE (company_id, source_type, source_id)
        )
    """)


def _sync_expense_to_accounting(cur, expense_id, company_id):
    """Создаёт или обновляет бухгалтерскую операцию для одного расхода."""
    _ensure_accounting_operations_table(cur)

    cur.execute("""
        SELECT
            id, company_id, user_id, category, description,
            amount, payment_method, date, created_at
        FROM expenses
        WHERE id = %s AND company_id = %s
    """, (expense_id, company_id))
    expense = cur.fetchone()

    if not expense:
        return

    cur.execute("""
        INSERT INTO accounting_operations (
            company_id, user_id, source_type, source_id,
            operation_type, title, amount, payment_method,
            counterparty, operation_date, status,
            created_at, updated_at
        )
        VALUES (
            %s, %s, 'expense', %s,
            'expense', %s, %s, %s,
            NULL, %s, 'completed',
            %s, %s
        )
        ON CONFLICT (company_id, source_type, source_id)
        DO UPDATE SET
            user_id = EXCLUDED.user_id,
            title = EXCLUDED.title,
            amount = EXCLUDED.amount,
            payment_method = EXCLUDED.payment_method,
            operation_date = EXCLUDED.operation_date,
            status = EXCLUDED.status,
            updated_at = EXCLUDED.updated_at
    """, (
        company_id,
        expense["user_id"],
        expense["id"],
        f"{expense['category']}: {expense['description']}",
        expense["amount"],
        expense["payment_method"],
        expense["date"],
        expense["created_at"] or now_kz(),
        now_kz(),
    ))


def _delete_expense_from_accounting(cur, expense_id, company_id):
    if not expense_id:
        return

    _ensure_accounting_operations_table(cur)
    cur.execute("""
        DELETE FROM accounting_operations
        WHERE company_id = %s
          AND source_type = 'expense'
          AND source_id = %s
    """, (company_id, expense_id))


def upsert_expense_from_source(
    cur,
    *,
    company_id,
    source_type,
    source_id,
    category,
    description,
    amount,
    expense_date,
    payment_method=None,
    comment=None,
    user_id=None,
):
    """
    Создаёт или обновляет автоматический расход.

    Вызывайте эту функцию из прихода, зарплаты, налогов и других модулей.
    Повторный вызов не создаст дубль благодаря уникальному source_type/source_id.
    """
    if source_type not in AUTOMATIC_SOURCE_TYPES:
        raise ValueError("Неизвестный источник автоматического расхода")

    if category not in EXPENSE_CATEGORIES:
        raise ValueError("Неизвестная категория расхода")

    amount = _parse_amount(amount)

    cur.execute("""
        INSERT INTO expenses (
            company_id,
            user_id,
            category,
            description,
            amount,
            payment_method,
            comment,
            date,
            created_at,
            updated_at,
            source_type,
            source_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (company_id, source_type, source_id)
        WHERE source_type IS NOT NULL AND source_id IS NOT NULL
        DO UPDATE SET
            user_id = EXCLUDED.user_id,
            category = EXCLUDED.category,
            description = EXCLUDED.description,
            amount = EXCLUDED.amount,
            payment_method = EXCLUDED.payment_method,
            comment = EXCLUDED.comment,
            date = EXCLUDED.date,
            updated_at = EXCLUDED.updated_at
        RETURNING id
    """, (
        company_id,
        user_id,
        category,
        description,
        amount,
        payment_method,
        comment,
        expense_date,
        now_kz(),
        now_kz(),
        source_type,
        source_id,
    ))

    return cur.fetchone()["id"]


def delete_expense_by_source(cur, *, company_id, source_type, source_id):
    """Удаляет автоматический расход при отмене исходной операции."""
    cur.execute("""
        DELETE FROM expenses
        WHERE company_id = %s
          AND source_type = %s
          AND source_id = %s
        RETURNING id
    """, (company_id, source_type, source_id))
    row = cur.fetchone()
    return row["id"] if row else None


def _source_filter_sql(source):
    if source == "manual":
        return "source_type IS NULL"
    if source == "automatic":
        return "source_type IS NOT NULL"
    return None



def _parse_date(value, field_name="Дата"):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} указана неверно")


def _parse_amount(value):
    try:
        amount = Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Введите корректную сумму")

    if amount <= 0:
        raise ValueError("Сумма расхода должна быть больше нуля")

    return amount.quantize(Decimal("0.01"))


def _get_form_data():
    expense_date = _parse_date(request.form.get("date"))
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    amount = _parse_amount(request.form.get("amount"))
    payment_method = request.form.get("payment_method", "").strip()
    comment = request.form.get("comment", "").strip()

    if category not in EXPENSE_CATEGORIES:
        raise ValueError("Выберите корректную категорию")

    if not description:
        raise ValueError("Укажите описание расхода")

    if len(description) > 160:
        raise ValueError("Описание не должно превышать 160 символов")

    if payment_method not in PAYMENT_METHODS:
        raise ValueError("Выберите корректный способ оплаты")

    if len(comment) > 500:
        raise ValueError("Комментарий не должен превышать 500 символов")

    return {
        "date": expense_date,
        "category": category,
        "description": description,
        "amount": amount,
        "payment_method": payment_method,
        "comment": comment,
    }


def _error_response(message, status=400):
    """Для обычной HTML-формы показывает понятную ошибку."""
    return f"Расход не сохранён: {message}", status


@expenses_bp.route("/expenses")
def expenses():
    company_id = _require_company()

    if not session.get("user_id"):
        return redirect("/login")

    if not company_id:
        return "Активная компания не выбрана", 400

    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    source = request.args.get("source", "").strip()
    date_from_raw = request.args.get("date_from", "").strip()
    date_to_raw = request.args.get("date_to", "").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    date_from = None
    date_to = None

    try:
        if date_from_raw:
            date_from = _parse_date(date_from_raw, "Начальная дата")
        if date_to_raw:
            date_to = _parse_date(date_to_raw, "Конечная дата")
    except ValueError as exc:
        return _error_response(str(exc))

    if date_from and date_to and date_from > date_to:
        return _error_response("Начальная дата не может быть позже конечной")

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_expenses_table(cur)
        conn.commit()

        today = now_kz().date()
        month_start = today.replace(day=1)

        # Основные показатели страницы.
        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE company_id = %s
              AND date = %s
        """, (company_id, today))
        today_total = cur.fetchone()["total"] or 0

        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE company_id = %s
              AND date BETWEEN %s AND %s
        """, (company_id, month_start, today))
        month_total = cur.fetchone()["total"] or 0

        cur.execute("""
            SELECT category, COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE company_id = %s
              AND date BETWEEN %s AND %s
            GROUP BY category
            ORDER BY total DESC, category
        """, (company_id, month_start, today))
        month_category_rows = cur.fetchall()

        category_amounts = {
            row["category"]: row["total"] or 0
            for row in month_category_rows
        }

        category_totals = [
            {
                "category": category_name,
                "total": category_amounts.get(category_name, 0),
            }
            for category_name in EXPENSE_CATEGORIES
        ]

        if month_category_rows:
            largest_category = month_category_rows[0]["category"]
            largest_category_total = month_category_rows[0]["total"] or 0
        else:
            largest_category = "Нет данных"
            largest_category_total = 0

        # Фильтры таблицы.
        where_parts = ["company_id = %s"]
        params = [company_id]

        if search:
            where_parts.append("(description ILIKE %s OR comment ILIKE %s OR category ILIKE %s OR payment_method ILIKE %s)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

        if category:
            if category not in EXPENSE_CATEGORIES:
                return _error_response("Указана неизвестная категория")
            where_parts.append("category = %s")
            params.append(category)

        source_condition = _source_filter_sql(source)
        if source and not source_condition:
            return _error_response("Указан неизвестный источник расходов")
        if source_condition:
            where_parts.append(source_condition)

        if date_from:
            where_parts.append("date >= %s")
            params.append(date_from)

        if date_to:
            where_parts.append("date <= %s")
            params.append(date_to)

        where_sql = " AND ".join(where_parts)

        cur.execute(
            f"SELECT COUNT(*) AS total FROM expenses WHERE {where_sql}",
            tuple(params),
        )
        total_rows = int(cur.fetchone()["total"] or 0)

        pagination = Pagination(page=page, per_page=PER_PAGE, total=total_rows)

        if page > pagination.pages:
            page = pagination.pages
            pagination.page = page

        offset = (page - 1) * PER_PAGE

        cur.execute(
            f"""
                SELECT
                    id,
                    company_id,
                    user_id,
                    category,
                    description,
                    amount,
                    payment_method,
                    comment,
                    date,
                    created_at,
                    updated_at,
                    source_type,
                    source_id,
                    CASE WHEN source_type IS NULL THEN 'manual' ELSE 'automatic' END AS source,
                    CASE WHEN source_type IS NOT NULL THEN TRUE ELSE FALSE END AS is_automatic
                FROM expenses
                WHERE {where_sql}
                ORDER BY date DESC, id DESC
                LIMIT %s OFFSET %s
            """,
            tuple(params + [PER_PAGE, offset]),
        )
        expense_rows = cur.fetchall()

        return render_template(
            "expenses.html",
            expenses=expense_rows,
            categories=EXPENSE_CATEGORIES,
            category_totals=category_totals,
            today_total=today_total,
            month_total=month_total,
            largest_category=largest_category,
            largest_category_total=largest_category_total,
            total_expenses_count=total_rows,
            pagination=pagination,
        )

    except Exception as exc:
        conn.rollback()
        print("EXPENSES PAGE ERROR:", exc)
        return "Не удалось загрузить расходы", 500

    finally:
        cur.close()
        pool.putconn(conn)


@expenses_bp.route("/expenses/add", methods=["POST"])
def add_expense():
    company_id = _require_company()

    if not session.get("user_id"):
        return redirect("/login")

    if not company_id:
        return "Активная компания не выбрана", 400

    try:
        data = _get_form_data()
    except ValueError as exc:
        return _error_response(str(exc))

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_expenses_table(cur)

        cur.execute("""
            INSERT INTO expenses (
                company_id,
                user_id,
                category,
                description,
                amount,
                payment_method,
                comment,
                date,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            company_id,
            session.get("user_id"),
            data["category"],
            data["description"],
            data["amount"],
            data["payment_method"],
            data["comment"],
            data["date"],
            now_kz(),
        ))

        expense_id = cur.fetchone()["id"]
        _sync_expense_to_accounting(cur, expense_id, company_id)

        conn.commit()
        return redirect("/expenses")

    except Exception as exc:
        conn.rollback()
        print("ADD EXPENSE ERROR:", exc)
        return "Не удалось сохранить расход", 500

    finally:
        cur.close()
        pool.putconn(conn)


@expenses_bp.route("/expenses/<int:expense_id>/edit", methods=["POST"])
def edit_expense(expense_id):
    company_id = _require_company()

    if not session.get("user_id"):
        return redirect("/login")

    if not company_id:
        return "Активная компания не выбрана", 400

    try:
        data = _get_form_data()
    except ValueError as exc:
        return _error_response(str(exc))

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_expenses_table(cur)

        cur.execute("""
            SELECT source_type
            FROM expenses
            WHERE id = %s AND company_id = %s
        """, (expense_id, company_id))
        existing = cur.fetchone()

        if not existing:
            return "Расход не найден", 404

        if existing["source_type"]:
            return "Автоматический расход изменяется в исходном разделе", 409

        cur.execute("""
            UPDATE expenses
            SET
                category = %s,
                description = %s,
                amount = %s,
                payment_method = %s,
                comment = %s,
                date = %s,
                updated_at = %s
            WHERE id = %s
              AND company_id = %s
            RETURNING id
        """, (
            data["category"],
            data["description"],
            data["amount"],
            data["payment_method"],
            data["comment"],
            data["date"],
            now_kz(),
            expense_id,
            company_id,
        ))

        updated = cur.fetchone()

        if not updated:
            conn.rollback()
            return "Расход не найден", 404

        _sync_expense_to_accounting(cur, expense_id, company_id)

        conn.commit()
        return redirect("/expenses")

    except Exception as exc:
        conn.rollback()
        print("EDIT EXPENSE ERROR:", exc)
        return "Не удалось изменить расход", 500

    finally:
        cur.close()
        pool.putconn(conn)


@expenses_bp.route("/expenses/<int:expense_id>/delete", methods=["POST"])
def delete_expense(expense_id):
    company_id = _require_company()

    if not session.get("user_id"):
        return redirect("/login")

    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_expenses_table(cur)

        cur.execute("""
            SELECT source_type
            FROM expenses
            WHERE id = %s AND company_id = %s
        """, (expense_id, company_id))
        existing = cur.fetchone()

        if not existing:
            return "Расход не найден", 404

        if existing["source_type"]:
            return "Автоматический расход удаляется в исходном разделе", 409

        cur.execute("""
            DELETE FROM expenses
            WHERE id = %s
              AND company_id = %s
            RETURNING id
        """, (expense_id, company_id))

        deleted = cur.fetchone()

        if not deleted:
            conn.rollback()
            return "Расход не найден", 404

        _delete_expense_from_accounting(cur, expense_id, company_id)

        conn.commit()
        return redirect("/expenses")

    except Exception as exc:
        conn.rollback()
        print("DELETE EXPENSE ERROR:", exc)
        return "Не удалось удалить расход", 500

    finally:
        cur.close()
        pool.putconn(conn)