from datetime import datetime, date
from calendar import monthrange
from decimal import Decimal, InvalidOperation
import hashlib
import json
from io import BytesIO
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    send_file,
    session,
)
from werkzeug.utils import secure_filename

from models import get_db, pool
from utils.timezone import now_kz


accounting_bp = Blueprint("accounting", __name__)

ALLOWED_DOCUMENT_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png"
}

DOCUMENT_TYPES = {
    "invoice": "Счёт",
    "act": "Акт",
    "waybill": "Накладная",
    "invoice_facture": "Счёт-фактура",
    "report": "Налоговая отчётность",
    "payment": "Платёжный документ",
    "check": "Кассовый чек",
    "refund_check": "Чек возврата",
    "esf": "ЭСФ",
    "other": "Прочее",
}

MONTHS_RU = {
    1: "ЯНВ", 2: "ФЕВ", 3: "МАР", 4: "АПР", 5: "МАЙ", 6: "ИЮН",
    7: "ИЮЛ", 8: "АВГ", 9: "СЕН", 10: "ОКТ", 11: "НОЯ", 12: "ДЕК",
}


def _require_company():
    if not session.get("user_id"):
        return None
    return session.get("company_id")


def _upload_directory():
    configured = current_app.config.get("ACCOUNTING_UPLOAD_FOLDER")
    path = Path(configured) if configured else Path(current_app.root_path) / "uploads" / "accounting"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _allowed_file(filename):
    return bool(filename) and "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS


def _save_uploaded_file(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None
    if not _allowed_file(file_storage.filename):
        raise ValueError("Разрешены только PDF, Word, Excel и изображения JPG/PNG")

    original_name = secure_filename(file_storage.filename)
    extension = original_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid4().hex}.{extension}"
    file_storage.save(_upload_directory() / stored_name)
    return stored_name, original_name


def _delete_stored_file(stored_name):
    if not stored_name:
        return
    path = _upload_directory() / stored_name
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError as exc:
        print("ACCOUNTING FILE DELETE ERROR:", exc)


def _parse_date(value, field_name="Дата"):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} указана неверно")


def _parse_amount(value, required=False):
    raw = str(value or "").replace(" ", "").replace(",", ".").strip()
    if not raw:
        if required:
            raise ValueError("Введите сумму")
        return None

    try:
        amount = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Введите корректную сумму")

    if amount < 0 or (required and amount <= 0):
        raise ValueError("Сумма должна быть больше нуля")

    return amount.quantize(Decimal("0.01"))


def _ensure_accounting_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounting_documents (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            title TEXT NOT NULL,
            document_type TEXT NOT NULL,
            document_number TEXT,
            document_date DATE NOT NULL,
            amount NUMERIC(14, 2),
            counterparty TEXT,
            comment TEXT,
            stored_filename TEXT,
            original_filename TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP,
            archived_at TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounting_documents_company
        ON accounting_documents (company_id, document_date DESC, id DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounting_documents_status
        ON accounting_documents (company_id, status)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounting_tax_events (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            due_date DATE NOT NULL,
            amount NUMERIC(14, 2),
            status TEXT NOT NULL DEFAULT 'planned',
            paid_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounting_tax_events_company
        ON accounting_tax_events (company_id, due_date, id)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounting_debts (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            due_date DATE NOT NULL,
            amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
            status TEXT NOT NULL DEFAULT 'debt',
            paid_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounting_debts_company
        ON accounting_debts (company_id, status, due_date, id)
    """)

    # Связь документов с исходными модулями.
    cur.execute("ALTER TABLE accounting_documents ADD COLUMN IF NOT EXISTS source_type TEXT")
    cur.execute("ALTER TABLE accounting_documents ADD COLUMN IF NOT EXISTS source_id INTEGER")
    cur.execute("ALTER TABLE accounting_documents ADD COLUMN IF NOT EXISTS file_url TEXT")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_accounting_document_source
        ON accounting_documents (company_id, source_type, source_id, document_type)
        WHERE source_type IS NOT NULL AND source_id IS NOT NULL
    """)

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
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounting_operations_company_date
        ON accounting_operations (company_id, operation_date DESC, id DESC)
    """)

    # Реестр ФНО и неизменяемый журнал обмена с интеграционным шлюзом ИСНА.
    # Сам ключ ЭЦП здесь не хранится: браузер передаёт только подпись документа.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounting_filings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            form_type VARCHAR(10) NOT NULL,
            report_year INTEGER NOT NULL,
            report_period VARCHAR(10) NOT NULL,
            form_version VARCHAR(40),
            form_revision VARCHAR(40),
            payload JSONB NOT NULL,
            payload_hash VARCHAR(64) NOT NULL,
            signature TEXT,
            certificate_subject TEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'prepared',
            external_id TEXT,
            registration_number TEXT,
            response_payload JSONB,
            error_message TEXT,
            prepared_at TIMESTAMP NOT NULL,
            signed_at TIMESTAMP,
            sent_at TIMESTAMP,
            accepted_at TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE (company_id, form_type, report_year, report_period)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounting_filings_company_status
        ON accounting_filings (company_id, status, prepared_at DESC)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounting_filing_events (
            id SERIAL PRIMARY KEY,
            filing_id INTEGER NOT NULL REFERENCES accounting_filings(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            event_type VARCHAR(40) NOT NULL,
            from_status VARCHAR(30),
            to_status VARCHAR(30) NOT NULL,
            details JSONB,
            created_at TIMESTAMP NOT NULL
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounting_filing_events_filing
        ON accounting_filing_events (filing_id, created_at DESC, id DESC)
    """)



def _table_exists(cur, table_name):
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        ) AS exists
    """, (table_name,))
    return bool(cur.fetchone()["exists"])


def _column_exists(cur, table_name, column_name):
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
        ) AS exists
    """, (table_name, column_name))
    return bool(cur.fetchone()["exists"])


def _sale_payment_label(sale):
    sale_type = sale.get("sale_type") if hasattr(sale, "get") else sale["sale_type"]
    labels = {
        "cash": "Наличные",
        "card": "Банковская карта",
        "kaspi": "Kaspi",
        "invoice": "Расчётный счёт",
    }
    return labels.get(sale_type, sale_type or "Не указан")


def _sync_sales(cur, company_id):
    if not _table_exists(cur, "sales"):
        return

    has_is_refunded = _column_exists(cur, "sales", "is_refunded")
    has_refunded_at = _column_exists(cur, "sales", "refunded_at")
    refunded_sql = "COALESCE(s.is_refunded, FALSE)" if has_is_refunded else "FALSE"
    refunded_at_sql = "s.refunded_at" if has_refunded_at else "s.created_at"

    cur.execute(f"""
        SELECT
            s.id,
            s.user_id,
            s.sale_number,
            s.total_amount,
            s.status,
            s.sale_type,
            s.created_at,
            {refunded_at_sql} AS refunded_at,
            {refunded_sql} AS is_refunded,
            COALESCE(c.company_name, c.full_name, 'Без клиента') AS counterparty
        FROM sales s
        LEFT JOIN clients c ON c.id = s.client_id
        WHERE s.company_id = %s
          AND (s.status IN ('Оплачено', 'Возврат') OR {refunded_sql} = TRUE)
        ORDER BY s.id
    """, (company_id,))

    for sale in cur.fetchall():
        is_refund = sale["status"] == "Возврат" or bool(sale["is_refunded"])
        # Продажа и возврат — две самостоятельные денежные операции. Доходная
        # запись сохраняется, а возврат добавляется с собственной датой.
        operation_type = "income"
        source_type = "sale"
        title = f"Продажа №{sale['sale_number'] or sale['id']}"
        document_url = (
            f"/docs/invoice/{sale['id']}"
            if sale["sale_type"] == "invoice"
            else f"/docs/check/{sale['id']}"
        )

        cur.execute("""
            INSERT INTO accounting_operations (
                company_id, user_id, source_type, source_id, operation_type,
                title, amount, payment_method, counterparty,
                operation_date, document_url, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                    DATE(%s), %s, 'completed', %s, %s)
            ON CONFLICT (company_id, source_type, source_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                amount = EXCLUDED.amount,
                payment_method = EXCLUDED.payment_method,
                counterparty = EXCLUDED.counterparty,
                operation_date = EXCLUDED.operation_date,
                document_url = EXCLUDED.document_url,
                updated_at = EXCLUDED.updated_at
        """, (
            company_id,
            sale.get("user_id"),
            source_type,
            sale["id"],
            operation_type,
            title,
            sale["total_amount"] or 0,
            _sale_payment_label(sale),
            sale["counterparty"],
            sale["created_at"],
            document_url,
            sale["created_at"],
            now_kz(),
        ))

        if is_refund:
            refund_date = sale.get("refunded_at") or sale["created_at"]
            cur.execute("""
                INSERT INTO accounting_operations (
                    company_id, user_id, source_type, source_id, operation_type,
                    title, amount, payment_method, counterparty,
                    operation_date, document_url, status, created_at, updated_at
                )
                VALUES (%s, %s, 'sale_refund', %s, 'refund', %s, %s, %s, %s,
                        DATE(%s), %s, 'completed', %s, %s)
                ON CONFLICT (company_id, source_type, source_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    amount = EXCLUDED.amount,
                    payment_method = EXCLUDED.payment_method,
                    counterparty = EXCLUDED.counterparty,
                    operation_date = EXCLUDED.operation_date,
                    document_url = EXCLUDED.document_url,
                    updated_at = EXCLUDED.updated_at
            """, (
                company_id,
                sale.get("user_id"),
                sale["id"],
                f"Возврат по продаже №{sale['sale_number'] or sale['id']}",
                sale["total_amount"] or 0,
                _sale_payment_label(sale),
                sale["counterparty"],
                refund_date,
                f"/docs/refund-check/{sale['id']}",
                refund_date,
                now_kz(),
            ))

        # Документы продажи отображаются в бухгалтерском архиве как ссылки
        # на уже существующие автоматически формируемые шаблоны.
        documents = []

        # Исходные документы продажи сохраняются и после возврата.
        if True:
            # Для продажи по счёту доступен счёт на оплату.
            if sale["sale_type"] == "invoice":
                documents.append(
                    ("invoice", "Счёт на оплату", f"/docs/invoice/{sale['id']}")
                )
            else:
                # Для кассовой продажи доступен кассовый чек.
                documents.append(
                    ("check", "Кассовый чек", f"/docs/check/{sale['id']}")
                )

            # Эти первичные документы относятся к оплаченной продаже
            # независимо от способа оплаты.
            documents.extend([
                (
                    "waybill",
                    "Накладная",
                    f"/docs/nakladnaya/{sale['id']}",
                ),
                (
                    "act",
                    "Акт выполненных работ",
                    f"/docs/act/{sale['id']}",
                ),
                (
                    "invoice_facture",
                    "Счёт-фактура",
                    f"/docs/schet-factura/{sale['id']}",
                ),
            ])

        if is_refund and sale["sale_type"] != "invoice":
            documents.append((
                "refund_check",
                "Чек возврата",
                f"/docs/refund-check/{sale['id']}",
            ))

        for document_type, document_title, file_url in documents:
            cur.execute("""
                INSERT INTO accounting_documents (
                    company_id, user_id, title, document_type,
                    document_number, document_date, amount, counterparty,
                    comment, status, created_at,
                    source_type, source_id, file_url
                )
                VALUES (%s, %s, %s, %s, %s, DATE(%s), %s, %s,
                        %s, 'completed', %s, %s, %s, %s)
                ON CONFLICT (company_id, source_type, source_id, document_type)
                WHERE source_type IS NOT NULL AND source_id IS NOT NULL
                DO UPDATE SET
                    title = EXCLUDED.title,
                    document_number = EXCLUDED.document_number,
                    document_date = EXCLUDED.document_date,
                    amount = EXCLUDED.amount,
                    counterparty = EXCLUDED.counterparty,
                    file_url = EXCLUDED.file_url,
                    updated_at = %s
            """, (
                company_id,
                sale.get("user_id"),
                f"{document_title} №{sale['sale_number'] or sale['id']}",
                document_type,
                str(sale["sale_number"] or sale["id"]),
                sale["created_at"],
                sale["total_amount"] or 0,
                sale["counterparty"],
                "Создано автоматически из продажи",
                sale["created_at"],
                "sale",
                sale["id"],
                file_url,
                now_kz(),
            ))


def _sync_expenses(cur, company_id):
    if not _table_exists(cur, "expenses"):
        return

    date_column = "date" if _column_exists(cur, "expenses", "date") else "expense_date"
    description_column = (
        "description" if _column_exists(cur, "expenses", "description") else "title"
    )

    cur.execute(f"""
        SELECT
            id,
            user_id,
            category,
            {description_column} AS description,
            amount,
            payment_method,
            {date_column} AS operation_date,
            created_at
        FROM expenses
        WHERE company_id = %s
        ORDER BY id
    """, (company_id,))

    for expense in cur.fetchall():
        cur.execute("""
            INSERT INTO accounting_operations (
                company_id, user_id, source_type, source_id, operation_type,
                title, amount, payment_method, counterparty,
                operation_date, status, created_at, updated_at
            )
            VALUES (%s, %s, 'expense', %s, 'expense', %s, %s, %s, NULL,
                    %s, 'completed', %s, %s)
            ON CONFLICT (company_id, source_type, source_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                amount = EXCLUDED.amount,
                payment_method = EXCLUDED.payment_method,
                operation_date = EXCLUDED.operation_date,
                updated_at = EXCLUDED.updated_at
        """, (
            company_id,
            expense.get("user_id"),
            expense["id"],
            f"{expense['category']}: {expense['description']}",
            expense["amount"] or 0,
            expense["payment_method"],
            expense["operation_date"],
            expense.get("created_at") or now_kz(),
            now_kz(),
        ))


def _sync_accounting(cur, company_id):
    _sync_sales(cur, company_id)
    _sync_expenses(cur, company_id)


def _operation_view(row):
    labels = {
        "income": "Доход",
        "expense": "Расход",
        "refund": "Возврат",
    }
    return {
        "id": row["id"],
        "type": row["operation_type"],
        "type_label": labels.get(row["operation_type"], row["operation_type"]),
        "title": row["title"],
        "amount": row["amount"],
        "payment_method": row["payment_method"] or "—",
        "counterparty": row["counterparty"] or "—",
        "date": row["operation_date"].strftime("%d.%m.%Y"),
        "document_url": row["document_url"],
    }

def _accounting_sale_groups(cur, company_id):
    """Единый журнал продаж для бухгалтерии: одна продажа = одна строка.

    Первичные документы не выводятся отдельными строками. Они собираются
    внутри продажи, а продажи делятся только на кассовые и выставленные
    через счёт на оплату.
    """
    if not _table_exists(cur, "sales"):
        return []

    has_is_refunded = _column_exists(cur, "sales", "is_refunded")
    has_refunded_at = _column_exists(cur, "sales", "refunded_at")
    has_sale_number = _column_exists(cur, "sales", "sale_number")
    has_sale_type = _column_exists(cur, "sales", "sale_type")
    has_esf = _table_exists(cur, "esf_documents")
    has_sale_item_type = _column_exists(cur, "sale_items", "item_type")
    item_type_expr = (
        "COALESCE(NULLIF(si.item_type, ''), i.item_type, 'product')"
        if has_sale_item_type
        else "COALESCE(i.item_type, 'product')"
    )

    refunded_sql = "COALESCE(s.is_refunded, FALSE)" if has_is_refunded else "FALSE"
    refunded_at_sql = "s.refunded_at" if has_refunded_at else "NULL::timestamp"
    sale_number_sql = "s.sale_number" if has_sale_number else "NULL::integer"
    sale_type_sql = "COALESCE(s.sale_type, 'cash')" if has_sale_type else "'cash'::text"
    esf_join = ""
    esf_select = "NULL::text AS esf_status, NULL::text AS esf_external_id, NULL::text AS esf_registration_number"
    if has_esf:
        esf_join = "LEFT JOIN esf_documents ed ON ed.company_id = s.company_id AND ed.sale_id = s.id"
        esf_select = "ed.status AS esf_status, ed.external_id AS esf_external_id, ed.registration_number AS esf_registration_number"

    cur.execute(f"""
        SELECT
            s.id,
            {sale_number_sql} AS sale_number,
            s.client_id,
            s.total_amount,
            s.paid_amount,
            s.status,
            {sale_type_sql} AS sale_type,
            s.created_at,
            {refunded_sql} AS is_refunded,
            {refunded_at_sql} AS refunded_at,
            c.full_name AS client_full_name,
            c.company_name AS client_company_name,
            COALESCE(doc_mix.product_count, 0) AS product_count,
            COALESCE(doc_mix.service_count, 0) AS service_count,
            COALESCE(doc_mix.product_total, 0) AS product_total,
            COALESCE(doc_mix.service_total, 0) AS service_total,
            {esf_select}
        FROM sales s
        LEFT JOIN clients c ON c.id = s.client_id
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (WHERE {item_type_expr} <> 'service') AS product_count,
                COUNT(*) FILTER (WHERE {item_type_expr} = 'service') AS service_count,
                COALESCE(SUM(si.total) FILTER (WHERE {item_type_expr} <> 'service'), 0) AS product_total,
                COALESCE(SUM(si.total) FILTER (WHERE {item_type_expr} = 'service'), 0) AS service_total
            FROM sale_items si
            LEFT JOIN items i ON i.id = si.item_id
            WHERE si.sale_id = s.id
        ) doc_mix ON TRUE
        {esf_join}
        WHERE s.company_id = %s
        ORDER BY s.created_at DESC, s.id DESC
        LIMIT 250
    """, (company_id,))

    payment_labels = {
        "cash": "Наличные",
        "card": "Карта",
        "kaspi": "Kaspi POS",
        "invoice": "Счёт на оплату",
    }
    esf_labels = {
        "draft": "Черновик",
        "prepared": "Готова к подписи",
        "signed": "Подписана",
        "sending": "Отправляется",
        "sent": "Отправлена",
        "accepted": "Принята",
        "failed": "Ошибка",
        "revoke_pending": "Отзыв ожидает",
        "revoking": "Отзывается",
        "revoked": "Отозвана",
        "revoke_failed": "Ошибка отзыва",
    }

    result = []
    for row in cur.fetchall():
        sale_id = row["id"]
        sale_number = row.get("sale_number") or sale_id
        sale_type = row.get("sale_type") or "cash"
        is_invoice = sale_type == "invoice"
        is_refunded = bool(row.get("is_refunded")) or row.get("status") == "Возврат"
        client_company = (row.get("client_company_name") or "").strip()
        client_name = (row.get("client_full_name") or "").strip()
        client_primary = client_company or client_name or "Частное лицо"
        client_secondary = client_name if client_company and client_name and client_name != client_company else ""

        if is_invoice:
            main_label = "Открыть счёт"
            main_title = "Счёт на оплату"
            main_url = f"/docs/invoice/{sale_id}"
        elif is_refunded:
            main_label = "Чек возврата"
            main_title = "Чек возврата"
            main_url = f"/docs/refund-check/{sale_id}"
        else:
            main_label = "Открыть чек"
            main_title = "Кассовый чек"
            main_url = f"/docs/check/{sale_id}"

        status_label = "Возвращён" if is_refunded else (row.get("status") or ("Выставлен" if is_invoice else "Продажа"))
        esf_status = row.get("esf_status") or ""
        product_count = int(row.get("product_count") or 0)
        service_count = int(row.get("service_count") or 0)
        # Основной документ + счёт-фактура + ЭСФ + документы по типам строк.
        documents_count = 3 + (1 if product_count else 0) + (1 if service_count else 0)

        created_at = row.get("created_at")
        result.append({
            "id": sale_id,
            "number": str(sale_number),
            "bucket": "invoice" if is_invoice else "receipt",
            "date": created_at.strftime("%d.%m.%Y") if created_at else "—",
            "time": created_at.strftime("%H:%M") if created_at else "",
            "amount": float(row.get("total_amount") or 0),
            "payment_method": payment_labels.get(sale_type, sale_type or "—"),
            "status": "refunded" if is_refunded else ("invoice" if is_invoice else "completed"),
            "status_label": status_label,
            "client_primary": client_primary,
            "client_secondary": client_secondary,
            "main_label": main_label,
            "main_title": main_title,
            "main_url": main_url,
            "product_count": product_count,
            "service_count": service_count,
            "product_total": float(row.get("product_total") or 0),
            "service_total": float(row.get("service_total") or 0),
            "documents_count": documents_count,
            "waybill_url": f"/docs/nakladnaya/{sale_id}" if product_count else "",
            "act_url": f"/docs/act/{sale_id}" if service_count else "",
            "invoice_facture_url": f"/docs/schet-factura/{sale_id}",
            "esf_status": esf_status,
            "esf_status_label": esf_labels.get(esf_status, "Не создана"),
            "esf_external_id": row.get("esf_external_id") or "",
            "esf_registration_number": row.get("esf_registration_number") or "",
            "esf_url": f"/sales?esf_sale={sale_id}",
        })
    return result


def _document_view(row):
    status = row["status"] or "active"
    status_labels = {
        "active": "Добавлен",
        "completed": "Проведён",
        "archived": "В архиве",
    }

    return {
        "id": row["id"],
        "title": row["title"],
        "number": row["document_number"],
        "date": row["document_date"].strftime("%d.%m.%Y"),
        "amount": row["amount"],
        "type": "archive" if status == "archived" else row["document_type"],
        "document_type": row["document_type"],
        "type_label": DOCUMENT_TYPES.get(row["document_type"], "Документ"),
        "status": status,
        "status_label": status_labels.get(status, "Добавлен"),
        "counterparty": row["counterparty"],
        "comment": row["comment"],
        "file_url": row.get("file_url") or (f"/accounting/files/{row['stored_filename']}" if row["stored_filename"] else None),
    }


def _tax_event_view(row, today):
    status = row["status"] or "planned"
    if status != "paid" and row["due_date"] < today:
        visual_status, status_label = "overdue", "Просрочено"
    elif status == "paid":
        visual_status, status_label = "paid", "Оплачено"
    else:
        visual_status, status_label = "planned", "Запланировано"

    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "amount": row["amount"],
        "due_date": row["due_date"],
        "day": row["due_date"].strftime("%d"),
        "month": MONTHS_RU[row["due_date"].month],
        "status": visual_status,
        "status_label": status_label,
    }


def _debt_view(row, today):
    status = row["status"] or "debt"
    if status == "paid":
        visual_status, status_label = "paid", "Оплачено"
    elif row["due_date"] < today:
        visual_status, status_label = "overdue", "Просрочено"
    else:
        visual_status, status_label = "debt", "К оплате"

    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "amount": row["amount"],
        "due_date": row["due_date"].strftime("%d.%m.%Y"),
        "status": visual_status,
        "status_label": status_label,
        "icon": "✓" if status == "paid" else "₸",
    }




def _ensure_tax_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounting_tax_settings (
            company_id INTEGER PRIMARY KEY,
            regime VARCHAR(40) NOT NULL DEFAULT 'simplified',
            turnover_rate NUMERIC(7,4) NOT NULL DEFAULT 4,
            mzp NUMERIC(14,2) NOT NULL DEFAULT 85000,
            mrp NUMERIC(14,2) NOT NULL DEFAULT 4325,
            owner_base NUMERIC(14,2) NOT NULL DEFAULT 85000,
            owner_opv_rate NUMERIC(7,4) NOT NULL DEFAULT 10,
            owner_so_rate NUMERIC(7,4) NOT NULL DEFAULT 5,
            owner_vosms_rate NUMERIC(7,4) NOT NULL DEFAULT 5,
            employee_opv_rate NUMERIC(7,4) NOT NULL DEFAULT 10,
            employee_vosms_rate NUMERIC(7,4) NOT NULL DEFAULT 2,
            employee_ipn_rate NUMERIC(7,4) NOT NULL DEFAULT 10,
            employer_so_rate NUMERIC(7,4) NOT NULL DEFAULT 5,
            employer_osms_rate NUMERIC(7,4) NOT NULL DEFAULT 3,
            employer_opvr_rate NUMERIC(7,4) NOT NULL DEFAULT 3.5,
            standard_deduction NUMERIC(14,2) NOT NULL DEFAULT 0,
            include_owner_opvr BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee_tax_profiles (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            salary NUMERIC(14,2) NOT NULL DEFAULT 85000,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            use_standard_deduction BOOLEAN NOT NULL DEFAULT TRUE,
            is_pensioner BOOLEAN NOT NULL DEFAULT FALSE,
            is_exempt_vosms BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP,
            UNIQUE(company_id, user_id)
        )
    """)
    cur.execute("ALTER TABLE accounting_debts ADD COLUMN IF NOT EXISTS tax_key TEXT")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounting_debts_tax_key
        ON accounting_debts(company_id, tax_key)
        WHERE tax_key IS NOT NULL
    """)


def _month_bounds(period):
    try:
        year, month = [int(x) for x in period.split('-', 1)]
        start = date(year, month, 1)
    except Exception:
        today = now_kz().date()
        start = today.replace(day=1)
    end = date(start.year, start.month, monthrange(start.year, start.month)[1])
    if start.month == 12:
        due = date(start.year + 1, 1, 25)
    else:
        due = date(start.year, start.month + 1, 25)
    return start, end, due


def _get_tax_settings(cur, company_id):
    cur.execute("SELECT * FROM accounting_tax_settings WHERE company_id=%s", (company_id,))
    row = cur.fetchone()
    if row:
        return row
    cur.execute("""
        INSERT INTO accounting_tax_settings(company_id, updated_at)
        VALUES (%s, %s)
        RETURNING *
    """, (company_id, now_kz()))
    return cur.fetchone()


def _calculate_taxes(cur, company_id, period):
    start, end, due_date = _month_bounds(period)
    settings = _get_tax_settings(cur, company_id)

    cur.execute("""
        SELECT COALESCE(SUM(total_amount),0) AS income
        FROM sales
        WHERE company_id=%s
          AND status='Оплачено'
          AND DATE(created_at) BETWEEN %s AND %s
    """, (company_id, start, end))
    income = float(cur.fetchone()['income'] or 0)

    cur.execute("""
        SELECT COALESCE(SUM(total_amount),0) AS refunds
        FROM sales
        WHERE company_id=%s
          AND (status='Возврат' OR COALESCE(is_refunded,FALSE)=TRUE)
          AND DATE(created_at) BETWEEN %s AND %s
    """, (company_id, start, end))
    refunds = float(cur.fetchone()['refunds'] or 0)
    taxable_income = max(income - refunds, 0)

    turnover_rate = float(settings['turnover_rate'] or 0)
    turnover_tax = taxable_income * turnover_rate / 100

    owner_base = float(settings['owner_base'] or settings['mzp'] or 0)
    owner_opv = owner_base * float(settings['owner_opv_rate'] or 0) / 100
    owner_so = owner_base * float(settings['owner_so_rate'] or 0) / 100
    owner_vosms = float(settings['mzp'] or 0) * 1.4 * float(settings['owner_vosms_rate'] or 0) / 100
    owner_opvr = owner_base * float(settings['employer_opvr_rate'] or 0) / 100 if settings['include_owner_opvr'] else 0

    cur.execute("""
        SELECT p.*, COALESCE(u.full_name,u.username) AS employee_name
        FROM employee_tax_profiles p
        JOIN users u ON u.id=p.user_id
        WHERE p.company_id=%s AND p.is_active=TRUE
        ORDER BY employee_name
    """, (company_id,))
    employees=[]
    totals={'opv':0,'vosms':0,'ipn':0,'so':0,'osms':0,'opvr':0,'salary':0}
    for row in cur.fetchall():
        salary=float(row['salary'] or 0)
        opv=0 if row['is_pensioner'] else salary*float(settings['employee_opv_rate'] or 0)/100
        vosms=0 if row['is_exempt_vosms'] else salary*float(settings['employee_vosms_rate'] or 0)/100
        deduction=float(settings['standard_deduction'] or 0) if row['use_standard_deduction'] else 0
        ipn=max(salary-opv-vosms-deduction,0)*float(settings['employee_ipn_rate'] or 0)/100
        so=salary*float(settings['employer_so_rate'] or 0)/100
        osms=0 if row['is_exempt_vosms'] else salary*float(settings['employer_osms_rate'] or 0)/100
        opvr=0 if row['is_pensioner'] else salary*float(settings['employer_opvr_rate'] or 0)/100
        item={'user_id':row['user_id'],'name':row['employee_name'],'salary':salary,'opv':opv,'vosms':vosms,'ipn':ipn,'so':so,'osms':osms,'opvr':opvr,'net_salary':salary-opv-vosms-ipn}
        employees.append(item)
        for k in totals: totals[k]+=item.get(k,0)

    owner_total=owner_opv+owner_so+owner_vosms+owner_opvr
    employee_total=totals['opv']+totals['vosms']+totals['ipn']+totals['so']+totals['osms']+totals['opvr']
    monthly_total=owner_total+employee_total
    return {
        'period': start.strftime('%Y-%m'), 'period_label': start.strftime('%m.%Y'),
        'date_from':start,'date_to':end,'due_date':due_date,
        'income':income,'refunds':refunds,'taxable_income':taxable_income,
        'turnover_rate':turnover_rate,'turnover_tax':turnover_tax,
        'owner':{'base':owner_base,'opv':owner_opv,'so':owner_so,'vosms':owner_vosms,'opvr':owner_opvr,'total':owner_total},
        'employees':employees,'employee_totals':totals,'employee_total':employee_total,
        'monthly_total':monthly_total,
        'settings':settings,
    }


@accounting_bp.route('/accounting/taxes/settings', methods=['POST'])
def save_tax_settings():
    if not session.get('user_id'): return redirect('/login')
    company_id=_require_company()
    conn=get_db(); cur=conn.cursor()
    try:
        _ensure_tax_tables(cur)
        fields=['turnover_rate','mzp','mrp','owner_base','owner_opv_rate','owner_so_rate','owner_vosms_rate','employee_opv_rate','employee_vosms_rate','employee_ipn_rate','employer_so_rate','employer_osms_rate','employer_opvr_rate','standard_deduction']
        values=[]
        for f in fields:
            try: values.append(float(request.form.get(f,0) or 0))
            except: values.append(0)
        cur.execute(f"""
            INSERT INTO accounting_tax_settings(company_id,{','.join(fields)},include_owner_opvr,updated_at)
            VALUES (%s,{','.join(['%s']*len(fields))},%s,%s)
            ON CONFLICT(company_id) DO UPDATE SET
            {','.join([f'{f}=EXCLUDED.{f}' for f in fields])},
            include_owner_opvr=EXCLUDED.include_owner_opvr,updated_at=EXCLUDED.updated_at
        """, [company_id,*values,request.form.get('include_owner_opvr')=='1',now_kz()])
        conn.commit(); return redirect('/accounting#taxesBlock')
    finally:
        cur.close(); pool.putconn(conn)


@accounting_bp.route('/accounting/taxes/employee', methods=['POST'])
def save_employee_tax_profile():
    if not session.get('user_id'): return redirect('/login')
    company_id=_require_company(); conn=get_db(); cur=conn.cursor()
    try:
        _ensure_tax_tables(cur)
        user_id=int(request.form['user_id']); salary=float(request.form.get('salary',0) or 0)
        cur.execute("""
            INSERT INTO employee_tax_profiles(company_id,user_id,salary,is_active,use_standard_deduction,is_pensioner,is_exempt_vosms,created_at,updated_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(company_id,user_id) DO UPDATE SET salary=EXCLUDED.salary,is_active=EXCLUDED.is_active,
            use_standard_deduction=EXCLUDED.use_standard_deduction,is_pensioner=EXCLUDED.is_pensioner,
            is_exempt_vosms=EXCLUDED.is_exempt_vosms,updated_at=EXCLUDED.updated_at
        """,(company_id,user_id,salary,request.form.get('is_active')=='1',request.form.get('use_standard_deduction')=='1',request.form.get('is_pensioner')=='1',request.form.get('is_exempt_vosms')=='1',now_kz(),now_kz()))
        conn.commit(); return redirect('/accounting#taxesBlock')
    finally:
        cur.close(); pool.putconn(conn)


@accounting_bp.route('/accounting/taxes/create-debts', methods=['POST'])
def create_tax_debts():
    if not session.get('user_id'): return redirect('/login')
    company_id=_require_company(); period=request.form.get('period') or now_kz().strftime('%Y-%m')
    conn=get_db(); cur=conn.cursor()
    try:
        _ensure_tax_tables(cur); calc=_calculate_taxes(cur,company_id,period)
        rows=[('owner_opv','ОПВ за ИП',calc['owner']['opv']),('owner_so','СО за ИП',calc['owner']['so']),('owner_vosms','ВОСМС за ИП',calc['owner']['vosms'])]
        if calc['owner']['opvr']>0: rows.append(('owner_opvr','ОПВР за ИП',calc['owner']['opvr']))
        t=calc['employee_totals']
        rows += [('emp_opv','ОПВ работников',t['opv']),('emp_vosms','ВОСМС работников',t['vosms']),('emp_ipn','ИПН работников',t['ipn']),('emp_so','СО работников',t['so']),('emp_osms','ОСМС работников',t['osms']),('emp_opvr','ОПВР работников',t['opvr'])]
        for key,title,amount in rows:
            if amount<=0: continue
            tax_key=f'{period}:{key}'
            cur.execute("""
                INSERT INTO accounting_debts(company_id,user_id,title,description,due_date,amount,status,created_at,tax_key)
                VALUES(%s,%s,%s,%s,%s,%s,'debt',%s,%s)
                ON CONFLICT(company_id,tax_key) WHERE tax_key IS NOT NULL DO UPDATE SET amount=EXCLUDED.amount,due_date=EXCLUDED.due_date,description=EXCLUDED.description,updated_at=%s
            """,(company_id,session.get('user_id'),title,f'Начисление за {calc["period_label"]}',calc['due_date'],amount,now_kz(),tax_key,now_kz()))
        conn.commit(); return redirect('/accounting#debtsBlock')
    except Exception as exc:
        conn.rollback(); print('CREATE TAX DEBTS ERROR:',exc); return 'Не удалось создать задолженности',500
    finally:
        cur.close(); pool.putconn(conn)

@accounting_bp.route("/accounting/sync", methods=["POST"])
def sync_accounting_data():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_accounting_tables(cur)
        _sync_accounting(cur, company_id)
        conn.commit()
        return redirect("/accounting?synced=1")
    except Exception as exc:
        conn.rollback()
        print("ACCOUNTING SYNC ERROR:", exc)
        return "Не удалось синхронизировать бухгалтерию", 500
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting")
def accounting():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()

    try:
        # Таблицы и историческая синхронизация больше не запускаются
        # при каждом открытии страницы. Это делает загрузку быстрой.      
        _ensure_accounting_tables(cur)
        _ensure_tax_tables(cur)
        conn.commit()
        
        today = now_kz().date()
        year_start = today.replace(month=1, day=1)
        year_end = today.replace(month=12, day=31)

        sale_groups = _accounting_sale_groups(cur, company_id)
        receipt_sales_count = sum(1 for sale in sale_groups if sale["bucket"] == "receipt")
        invoice_sales_count = sum(1 for sale in sale_groups if sale["bucket"] == "invoice")

        cur.execute("""
            SELECT *
            FROM accounting_operations
            WHERE company_id = %s
            ORDER BY operation_date DESC, id DESC
            LIMIT 100
        """, (company_id,))
        operations = [_operation_view(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT * FROM accounting_documents
            WHERE company_id = %s
              AND source_type IS NULL
            ORDER BY document_date DESC, id DESC
            LIMIT 200
        """, (company_id,))
        documents = [_document_view(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT * FROM accounting_tax_events
            WHERE company_id = %s
              AND (due_date >= %s OR status <> 'paid')
            ORDER BY CASE WHEN status = 'paid' THEN 1 ELSE 0 END, due_date ASC, id ASC
            LIMIT 12
        """, (company_id, today))
        tax_events = [_tax_event_view(row, today) for row in cur.fetchall()]

        cur.execute("""
            SELECT * FROM accounting_debts
            WHERE company_id = %s
            ORDER BY CASE WHEN status = 'paid' THEN 1 ELSE 0 END, due_date ASC, id DESC
            LIMIT 12
        """, (company_id,))
        debts = [_debt_view(row, today) for row in cur.fetchall()]

        cur.execute("""
            SELECT
                COALESCE((
                    SELECT SUM(amount)
                    FROM accounting_tax_events
                    WHERE company_id = %s
                      AND status <> 'paid'
                      AND due_date BETWEEN %s AND %s
                ), 0)
                +
                COALESCE((
                    SELECT SUM(amount)
                    FROM accounting_debts
                    WHERE company_id = %s
                      AND status <> 'paid'
                      AND tax_key IS NOT NULL
                      AND due_date BETWEEN %s AND %s
                ), 0) AS taxes_due,

                COALESCE((
                    SELECT SUM(amount)
                    FROM accounting_tax_events
                    WHERE company_id = %s
                      AND status = 'paid'
                      AND COALESCE(paid_at::date, due_date)
                          BETWEEN %s AND %s
                ), 0)
                +
                COALESCE((
                    SELECT SUM(amount)
                    FROM accounting_debts
                    WHERE company_id = %s
                      AND status = 'paid'
                      AND tax_key IS NOT NULL
                      AND COALESCE(paid_at::date, due_date)
                          BETWEEN %s AND %s
                ), 0) AS taxes_paid
        """, (
            company_id, year_start, year_end,
            company_id, year_start, year_end,
            company_id, year_start, year_end,
            company_id, year_start, year_end,
        ))
        tax_summary = cur.fetchone()

        cur.execute("""
            SELECT
                COALESCE(SUM(amount) FILTER (WHERE status <> 'paid'), 0) AS debt_total,
                COUNT(*) FILTER (WHERE status <> 'paid') AS debt_count
            FROM accounting_debts
            WHERE company_id = %s
        """, (company_id,))
        debt_summary = cur.fetchone()

        cur.execute("""
            SELECT
                COALESCE(SUM(amount) FILTER (WHERE operation_type = 'income'), 0) AS income_total,
                COALESCE(SUM(amount) FILTER (WHERE operation_type = 'expense'), 0) AS expense_total,
                COALESCE(SUM(amount) FILTER (WHERE operation_type = 'refund'), 0) AS refund_total
            FROM accounting_operations
            WHERE company_id = %s
        """, (company_id,))
        operation_summary = cur.fetchone()

        cur.execute("""
            SELECT
                COALESCE(SUM(total_amount) FILTER (
                    WHERE rekassa_ticket_id IS NOT NULL
                      AND status IN ('Оплачено', 'Возврат')), 0) AS fiscal_sales,
                COALESCE(SUM(total_amount) FILTER (
                    WHERE rekassa_ticket_id IS NOT NULL
                      AND (status = 'Возврат' OR COALESCE(is_refunded, FALSE) = TRUE)), 0) AS fiscal_refunds,
                COALESCE(SUM(GREATEST(total_amount - COALESCE(paid_amount, 0), 0)) FILTER (
                    WHERE status NOT IN ('Оплачено', 'Возврат')), 0) AS receivables
            FROM sales WHERE company_id = %s
        """, (company_id,))
        fiscal_summary = cur.fetchone() or {}

        cur.execute("""
            SELECT COUNT(*) AS documents_count
            FROM accounting_documents
            WHERE company_id = %s
        """, (company_id,))
        documents_count = cur.fetchone()["documents_count"] or 0

        cur.execute("""
            SELECT * FROM accounting_filings
            WHERE company_id=%s
            ORDER BY prepared_at DESC,id DESC LIMIT 12
        """, (company_id,))
        filings = cur.fetchall()

        selected_tax_period = request.args.get("tax_period") or now_kz().strftime("%Y-%m")
        tax_calculation = _calculate_taxes(cur, company_id, selected_tax_period)
        cur.execute("""
            SELECT id, COALESCE(full_name, username) AS name
            FROM users WHERE company_id=%s ORDER BY name
        """, (company_id,))
        tax_users = cur.fetchall()

        accounting_summary = {
            "income_total": operation_summary["income_total"] or 0,
            "expense_total": operation_summary["expense_total"] or 0,
            "refund_total": operation_summary["refund_total"] or 0,
            "balance": (operation_summary["income_total"] or 0)
                       - (operation_summary["expense_total"] or 0)
                       - (operation_summary["refund_total"] or 0),
            "taxes_due": tax_summary["taxes_due"] or 0,
            "taxes_paid": tax_summary["taxes_paid"] or 0,
            "debt_total": debt_summary["debt_total"] or 0,
            "debt_count": debt_summary["debt_count"] or 0,
            "documents_count": documents_count,
            "fiscal_sales": fiscal_summary.get("fiscal_sales") or 0,
            "fiscal_refunds": fiscal_summary.get("fiscal_refunds") or 0,
            "fiscal_net": (fiscal_summary.get("fiscal_sales") or 0)
                          - (fiscal_summary.get("fiscal_refunds") or 0),
            "receivables": fiscal_summary.get("receivables") or 0,
        }

        return render_template(
            "accounting.html",
            accounting_summary=accounting_summary,
            tax_events=tax_events,
            debts=debts,
            operations=operations,
            documents=documents,
            sale_groups=sale_groups,
            receipt_sales_count=receipt_sales_count,
            invoice_sales_count=invoice_sales_count,
            tax_calculation=tax_calculation,
            tax_users=tax_users,
            filings=filings,
        )

    except Exception as exc:
        conn.rollback()
        print("ACCOUNTING PAGE ERROR:", exc)
        return "Не удалось загрузить бухгалтерию", 500
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/documents/add", methods=["POST"])
def add_document():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    title = request.form.get("title", "").strip()
    document_type = request.form.get("type", "").strip()
    document_number = request.form.get("number", "").strip()
    counterparty = request.form.get("counterparty", "").strip()
    comment = request.form.get("comment", "").strip()

    if not title:
        return "Укажите название документа", 400
    if document_type not in DOCUMENT_TYPES:
        return "Выберите корректный тип документа", 400

    try:
        document_date = _parse_date(request.form.get("document_date"), "Дата документа")
        amount = _parse_amount(request.form.get("amount"))
        stored_filename, original_filename = _save_uploaded_file(request.files.get("file"))
    except ValueError as exc:
        return str(exc), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            INSERT INTO accounting_documents (
                company_id, user_id, title, document_type, document_number,
                document_date, amount, counterparty, comment,
                stored_filename, original_filename, status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s)
        """, (
            company_id, session.get("user_id"), title, document_type,
            document_number or None, document_date, amount,
            counterparty or None, comment or None,
            stored_filename, original_filename, now_kz(),
        ))
        conn.commit()
        return redirect("/accounting")
    except Exception as exc:
        conn.rollback()
        _delete_stored_file(stored_filename)
        print("ACCOUNTING ADD DOCUMENT ERROR:", exc)
        return "Не удалось сохранить документ", 500
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/documents/<int:document_id>/edit", methods=["POST"])
def edit_document(document_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    title = request.form.get("title", "").strip()
    document_type = request.form.get("type", "").strip()
    document_number = request.form.get("number", "").strip()
    counterparty = request.form.get("counterparty", "").strip()
    comment = request.form.get("comment", "").strip()

    if not title:
        return "Укажите название документа", 400
    if document_type not in DOCUMENT_TYPES:
        return "Выберите корректный тип документа", 400

    try:
        document_date = _parse_date(request.form.get("document_date"), "Дата документа")
        amount = _parse_amount(request.form.get("amount"))
    except ValueError as exc:
        return str(exc), 400

    conn = get_db()
    cur = conn.cursor()
    new_stored_name = None
    existing = None

    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            SELECT stored_filename, original_filename
            FROM accounting_documents
            WHERE id = %s AND company_id = %s
        """, (document_id, company_id))
        existing = cur.fetchone()

        if not existing:
            return "Документ не найден", 404

        uploaded_file = request.files.get("file")
        if uploaded_file and uploaded_file.filename:
            new_stored_name, new_original_name = _save_uploaded_file(uploaded_file)
        else:
            new_stored_name = existing["stored_filename"]
            new_original_name = existing["original_filename"]

        cur.execute("""
            UPDATE accounting_documents
            SET title = %s, document_type = %s, document_number = %s,
                document_date = %s, amount = %s, counterparty = %s,
                comment = %s, stored_filename = %s, original_filename = %s,
                updated_at = %s
            WHERE id = %s AND company_id = %s
        """, (
            title, document_type, document_number or None,
            document_date, amount, counterparty or None,
            comment or None, new_stored_name, new_original_name,
            now_kz(), document_id, company_id,
        ))

        conn.commit()

        if uploaded_file and uploaded_file.filename and existing["stored_filename"] != new_stored_name:
            _delete_stored_file(existing["stored_filename"])

        return redirect("/accounting")

    except ValueError as exc:
        conn.rollback()
        if new_stored_name and existing and new_stored_name != existing["stored_filename"]:
            _delete_stored_file(new_stored_name)
        return str(exc), 400
    except Exception as exc:
        conn.rollback()
        if new_stored_name and existing and new_stored_name != existing["stored_filename"]:
            _delete_stored_file(new_stored_name)
        print("ACCOUNTING EDIT DOCUMENT ERROR:", exc)
        return "Не удалось изменить документ", 500
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/documents/<int:document_id>/archive", methods=["POST"])
def archive_document(document_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            UPDATE accounting_documents
            SET status = 'archived', archived_at = %s, updated_at = %s
            WHERE id = %s AND company_id = %s
            RETURNING id
        """, (now_kz(), now_kz(), document_id, company_id))
        if not cur.fetchone():
            conn.rollback()
            return "Документ не найден", 404
        conn.commit()
        return redirect("/accounting")
    except Exception as exc:
        conn.rollback()
        print("ACCOUNTING ARCHIVE DOCUMENT ERROR:", exc)
        return "Не удалось отправить документ в архив", 500
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/documents/<int:document_id>/delete", methods=["POST"])
def delete_document(document_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            DELETE FROM accounting_documents
            WHERE id = %s AND company_id = %s
            RETURNING stored_filename
        """, (document_id, company_id))
        deleted = cur.fetchone()
        if not deleted:
            conn.rollback()
            return "Документ не найден", 404
        conn.commit()
        _delete_stored_file(deleted["stored_filename"])
        return redirect("/accounting")
    except Exception as exc:
        conn.rollback()
        print("ACCOUNTING DELETE DOCUMENT ERROR:", exc)
        return "Не удалось удалить документ", 500
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/documents/<int:document_id>/json")
def document_json(document_id):
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Требуется авторизация"}), 401

    company_id = _require_company()
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            SELECT * FROM accounting_documents
            WHERE id = %s AND company_id = %s
        """, (document_id, company_id))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Документ не найден"}), 404

        return jsonify({
            "success": True,
            "document": {
                "id": row["id"],
                "title": row["title"],
                "type": row["document_type"],
                "number": row["document_number"] or "",
                "document_date": row["document_date"].isoformat(),
                "amount": str(row["amount"] or ""),
                "counterparty": row["counterparty"] or "",
                "comment": row["comment"] or "",
            },
        })
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/files/<path:stored_filename>")
def accounting_file(stored_filename):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            SELECT original_filename
            FROM accounting_documents
            WHERE company_id = %s AND stored_filename = %s
        """, (company_id, stored_filename))
        document = cur.fetchone()
        if not document:
            return "Файл не найден", 404

        return send_from_directory(
            _upload_directory(),
            stored_filename,
            as_attachment=False,
            download_name=document["original_filename"] or stored_filename,
        )
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/tax-events/add", methods=["POST"])
def add_tax_event():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if not title:
        return "Укажите название налогового события", 400

    try:
        due_date = _parse_date(request.form.get("due_date"), "Срок")
        amount = _parse_amount(request.form.get("amount"))
    except ValueError as exc:
        return str(exc), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            INSERT INTO accounting_tax_events (
                company_id, user_id, title, description,
                due_date, amount, status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'planned', %s)
        """, (
            company_id, session.get("user_id"), title,
            description or None, due_date, amount, now_kz(),
        ))
        conn.commit()
        return redirect("/accounting")
    except Exception as exc:
        conn.rollback()
        print("ACCOUNTING ADD TAX EVENT ERROR:", exc)
        return "Не удалось добавить налоговое событие", 500
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/tax-events/<int:event_id>/paid", methods=["POST"])
def mark_tax_event_paid(event_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            UPDATE accounting_tax_events
            SET status = 'paid', paid_at = %s, updated_at = %s
            WHERE id = %s AND company_id = %s
            RETURNING id
        """, (now_kz(), now_kz(), event_id, company_id))
        if not cur.fetchone():
            conn.rollback()
            return "Событие не найдено", 404
        conn.commit()
        return redirect("/accounting")
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/tax-events/<int:event_id>/delete", methods=["POST"])
def delete_tax_event(event_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            DELETE FROM accounting_tax_events
            WHERE id = %s AND company_id = %s
        """, (event_id, company_id))
        conn.commit()
        return redirect("/accounting")
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/debts/add", methods=["POST"])
def add_debt():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if not title:
        return "Укажите название задолженности", 400

    try:
        due_date = _parse_date(request.form.get("due_date"), "Срок оплаты")
        amount = _parse_amount(request.form.get("amount"), required=True)
    except ValueError as exc:
        return str(exc), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            INSERT INTO accounting_debts (
                company_id, user_id, title, description,
                due_date, amount, status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'debt', %s)
        """, (
            company_id, session.get("user_id"), title,
            description or None, due_date, amount, now_kz(),
        ))
        conn.commit()
        return redirect("/accounting")
    except Exception as exc:
        conn.rollback()
        print("ACCOUNTING ADD DEBT ERROR:", exc)
        return "Не удалось добавить задолженность", 500
    finally:
        cur.close()
        pool.putconn(conn)



def _ensure_expenses_link_columns(cur):
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
            updated_at TIMESTAMP,
            source_type TEXT,
            source_id INTEGER
        )
    """)
    cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS source_type TEXT")
    cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS source_id INTEGER")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_expenses_source
        ON expenses(company_id, source_type, source_id)
        WHERE source_type IS NOT NULL AND source_id IS NOT NULL
    """)


def _create_expense_from_paid_debt(cur, debt, company_id):
    """Создаёт расход при оплате налога или другой задолженности."""
    _ensure_expenses_link_columns(cur)

    paid_date = now_kz().date()
    payment_method = "Расчётный счёт"

    cur.execute("""
        INSERT INTO expenses (
            company_id, user_id, category, description,
            amount, payment_method, comment, date,
            created_at, updated_at, source_type, source_id
        )
        VALUES (
            %s, %s, 'Налоги и обязательные платежи', %s,
            %s, %s, %s, %s,
            %s, %s, 'accounting_debt', %s
        )
        ON CONFLICT (company_id, source_type, source_id)
        WHERE source_type IS NOT NULL AND source_id IS NOT NULL
        DO UPDATE SET
            description = EXCLUDED.description,
            amount = EXCLUDED.amount,
            payment_method = EXCLUDED.payment_method,
            comment = EXCLUDED.comment,
            date = EXCLUDED.date,
            updated_at = EXCLUDED.updated_at
        RETURNING id
    """, (
        company_id,
        session.get("user_id"),
        debt["title"],
        debt["amount"],
        payment_method,
        debt.get("description") or "Создано автоматически при оплате задолженности",
        paid_date,
        now_kz(),
        now_kz(),
        debt["id"],
    ))
    expense_id = cur.fetchone()["id"]

    # Сразу отражаем расход в финансовом журнале.
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
            title = EXCLUDED.title,
            amount = EXCLUDED.amount,
            payment_method = EXCLUDED.payment_method,
            operation_date = EXCLUDED.operation_date,
            updated_at = EXCLUDED.updated_at
    """, (
        company_id,
        session.get("user_id"),
        expense_id,
        f"Налоги и обязательные платежи: {debt['title']}",
        debt["amount"],
        payment_method,
        paid_date,
        now_kz(),
        now_kz(),
    ))

@accounting_bp.route("/accounting/debts/<int:debt_id>/paid", methods=["POST"])
def mark_debt_paid(debt_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            UPDATE accounting_debts
            SET status = 'paid', paid_at = %s, updated_at = %s
            WHERE id = %s AND company_id = %s
            RETURNING id, title, description, amount, due_date, status
        """, (now_kz(), now_kz(), debt_id, company_id))

        debt = cur.fetchone()

        if not debt:
            conn.rollback()
            return "Задолженность не найдена", 404

        _create_expense_from_paid_debt(cur, debt, company_id)

        conn.commit()
        return redirect("/accounting")
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/debts/<int:debt_id>/delete", methods=["POST"])
def delete_debt(debt_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("""
            DELETE FROM accounting_debts
            WHERE id = %s AND company_id = %s
        """, (debt_id, company_id))
        conn.commit()
        return redirect("/accounting")
    finally:
        cur.close()
        pool.putconn(conn)


def _report_period_bounds(form_type, year, period):
    year = int(year)

    if form_type == "910":
        half = 1 if str(period) not in {"2", "II", "second"} else 2
        if half == 1:
            start = date(year, 1, 1)
            end = date(year, 6, 30)
            submit_due = date(year, 8, 15)
            payment_due = date(year, 8, 25)
            label = f"I полугодие {year}"
        else:
            start = date(year, 7, 1)
            end = date(year, 12, 31)
            submit_due = date(year + 1, 2, 15)
            payment_due = date(year + 1, 2, 25)
            label = f"II полугодие {year}"
        return start, end, submit_due, payment_due, label, half

    quarter = int(period) if str(period).isdigit() else 1
    quarter = min(max(quarter, 1), 4)
    month_from = (quarter - 1) * 3 + 1
    month_to = month_from + 2
    start = date(year, month_from, 1)
    end = date(year, month_to, monthrange(year, month_to)[1])

    if quarter == 4:
        submit_due = date(year + 1, 2, 15)
        payment_due = date(year + 1, 2, 25)
    else:
        submit_due = date(year, month_to + 2, 15)
        payment_due = date(year, month_to + 2, 25)

    label = f"{quarter} квартал {year}"
    return start, end, submit_due, payment_due, label, quarter


def _build_910_report(cur, company_id, year, half):
    start, end, submit_due, payment_due, label, half = _report_period_bounds(
        "910", year, half
    )
    settings = _get_tax_settings(cur, company_id)

    cur.execute("""
        SELECT
            COALESCE(SUM(total_amount) FILTER (
                WHERE status = 'Оплачено'
            ), 0) AS income,
            COALESCE(SUM(total_amount) FILTER (
                WHERE status = 'Возврат'
                   OR COALESCE(is_refunded, FALSE) = TRUE
            ), 0) AS refunds
        FROM sales
        WHERE company_id = %s
          AND DATE(created_at) BETWEEN %s AND %s
    """, (company_id, start, end))
    totals = cur.fetchone()

    income = float(totals["income"] or 0)
    refunds = float(totals["refunds"] or 0)
    taxable_income = max(income - refunds, 0)
    rate = float(settings["turnover_rate"] or 0)
    tax_amount = taxable_income * rate / 100

    months = []
    current = start
    while current <= end:
        month_end = date(
            current.year,
            current.month,
            monthrange(current.year, current.month)[1],
        )
        cur.execute("""
            SELECT
                COALESCE(SUM(total_amount) FILTER (
                    WHERE status = 'Оплачено'
                ), 0) AS income,
                COALESCE(SUM(total_amount) FILTER (
                    WHERE status = 'Возврат'
                       OR COALESCE(is_refunded, FALSE) = TRUE
                ), 0) AS refunds
            FROM sales
            WHERE company_id = %s
              AND DATE(created_at) BETWEEN %s AND %s
        """, (company_id, current, month_end))
        row = cur.fetchone()
        month_income = float(row["income"] or 0)
        month_refunds = float(row["refunds"] or 0)
        month_taxable = max(month_income - month_refunds, 0)
        months.append({
            "period": current.strftime("%Y-%m"),
            "label": current.strftime("%m.%Y"),
            "income": month_income,
            "refunds": month_refunds,
            "taxable_income": month_taxable,
            "tax": month_taxable * rate / 100,
        })
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    checks = [
        {
            "label": "Есть доход за период",
            "ok": income > 0,
            "message": "Продажи за период найдены" if income > 0 else "Доход за период равен нулю",
        },
        {
            "label": "Настроена ставка налога",
            "ok": rate > 0,
            "message": f"Ставка {rate:g}%" if rate > 0 else "Укажите ставку налога",
        },
    ]

    official_lines = [
        {
            "code": "910.00.001",
            "name": "Доход за налоговый период",
            "amount": income,
            "source": "Оплаченные продажи за полугодие",
            "note": "Сумма дохода до корректировок",
        },
        {
            "code": "910.00.002",
            "name": "Корректировка дохода",
            "amount": refunds,
            "source": "Возвраты за полугодие",
            "note": "Внутренний расчёт уменьшения дохода",
        },
        {
            "code": "910.00.003",
            "name": "Доход с учётом корректировки",
            "amount": taxable_income,
            "source": "910.00.001 − 910.00.002",
            "note": "База для расчёта налога",
        },
        {
            "code": "910.00.004",
            "name": "Исчисленный налог",
            "amount": tax_amount,
            "source": f"910.00.003 × {rate:g}%",
            "note": "Предварительный расчёт по настройкам компании",
        },
    ]

    return {
        "form_type": "910",
        "title": "Форма 910.00",
        "period_label": label,
        "date_from": start,
        "date_to": end,
        "submit_due": submit_due,
        "payment_due": payment_due,
        "income": income,
        "refunds": refunds,
        "taxable_income": taxable_income,
        "rate": rate,
        "tax_amount": tax_amount,
        "months": months,
        "checks": checks,
        "ready": all(item["ok"] for item in checks),
        "employee_count": 0,
        "official_lines": official_lines,
        "form_version": "27",
        "form_revision": "133",
    }


def _build_200_report(cur, company_id, year, quarter):
    start, end, submit_due, payment_due, label, quarter = _report_period_bounds(
        "200", year, quarter
    )

    months = []
    employee_map = {}
    totals = {
        "salary": 0,
        "opv": 0,
        "vosms": 0,
        "ipn": 0,
        "so": 0,
        "osms": 0,
        "opvr": 0,
        "net_salary": 0,
    }

    current = start
    while current <= end:
        calculation = _calculate_taxes(
            cur,
            company_id,
            current.strftime("%Y-%m"),
        )
        month_totals = calculation["employee_totals"]
        month_row = {
            "period": calculation["period"],
            "label": calculation["period_label"],
            "employee_count": len(calculation["employees"]),
            "salary": month_totals["salary"],
            "opv": month_totals["opv"],
            "vosms": month_totals["vosms"],
            "ipn": month_totals["ipn"],
            "so": month_totals["so"],
            "osms": month_totals["osms"],
            "opvr": month_totals["opvr"],
        }
        months.append(month_row)

        for key in totals:
            if key == "net_salary":
                totals[key] += sum(
                    float(employee["net_salary"] or 0)
                    for employee in calculation["employees"]
                )
            else:
                totals[key] += float(month_totals.get(key, 0) or 0)

        for employee in calculation["employees"]:
            item = employee_map.setdefault(employee["user_id"], {
                "user_id": employee["user_id"],
                "name": employee["name"],
                "salary": 0,
                "opv": 0,
                "vosms": 0,
                "ipn": 0,
                "so": 0,
                "osms": 0,
                "opvr": 0,
                "net_salary": 0,
            })
            for key in ("salary", "opv", "vosms", "ipn", "so", "osms", "opvr", "net_salary"):
                item[key] += float(employee.get(key, 0) or 0)

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    employees = list(employee_map.values())
    employee_count = len(employees)
    total_payments = (
        totals["opv"] + totals["vosms"] + totals["ipn"]
        + totals["so"] + totals["osms"] + totals["opvr"]
    )

    checks = [
        {
            "label": "Добавлены работники",
            "ok": employee_count > 0,
            "message": f"Работников: {employee_count}" if employee_count else "Нет работников в налоговом профиле",
        },
        {
            "label": "Указана зарплата",
            "ok": totals["salary"] > 0,
            "message": f"Начислено {totals['salary']:,.0f} ₸".replace(",", " ")
            if totals["salary"] > 0 else "Зарплата не начислена",
        },
    ]

    official_lines = [
        {
            "code": "200.00.001",
            "name": "Индивидуальный подоходный налог",
            "amount": totals["ipn"],
            "source": "Сумма ИПН по всем работникам за квартал",
            "note": "Итог квартала; помесячная расшифровка ниже",
        },
        {
            "code": "200.00.002",
            "name": "Обязательные пенсионные взносы",
            "amount": totals["opv"],
            "source": "ОПВ работников за квартал",
            "note": "Удержания из доходов работников",
        },
        {
            "code": "200.00.004",
            "name": "Социальные отчисления",
            "amount": totals["so"],
            "source": "СО работодателя за квартал",
            "note": "Начисления работодателя",
        },
        {
            "code": "200.00.006",
            "name": "Отчисления на ОСМС",
            "amount": totals["osms"],
            "source": "ОСМС работодателя за квартал",
            "note": "Начисления работодателя",
        },
        {
            "code": "200.00.007",
            "name": "Взносы на ОСМС",
            "amount": totals["vosms"],
            "source": "ВОСМС работников за квартал",
            "note": "Удержания из доходов работников",
        },
        {
            "code": "200.00.008",
            "name": "ОПВ работодателя",
            "amount": totals["opvr"],
            "source": "ОПВР за работников за квартал",
            "note": "Начисления работодателя",
        },
        {
            "code": "200.01",
            "name": "Расшифровка по физическим лицам",
            "amount": totals["salary"],
            "source": "Зарплата и начисления по каждому работнику",
            "note": f"Работников в расчёте: {employee_count}",
        },
    ]

    return {
        "form_type": "200",
        "title": "Форма 200.00",
        "period_label": label,
        "date_from": start,
        "date_to": end,
        "submit_due": submit_due,
        "payment_due": payment_due,
        "months": months,
        "employees": employees,
        "employee_count": employee_count,
        "totals": totals,
        "total_payments": total_payments,
        "checks": checks,
        "ready": all(item["ok"] for item in checks),
        "official_lines": official_lines,
        "form_version": "33",
        "form_revision": "142",
    }


@accounting_bp.route("/accounting/report")
def accounting_report():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    form_type = request.args.get("form_type", "910").strip()
    current_year = now_kz().year

    try:
        year = int(request.args.get("year") or current_year)
    except ValueError:
        year = current_year

    if form_type == "910":
        period = request.args.get("period", "1")
    elif form_type == "200":
        period = request.args.get("period", "1")
    else:
        return "Неизвестная форма отчётности", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        _ensure_tax_tables(cur)
        conn.commit()

        cur.execute("""
            SELECT id, name, bin, address, director
            FROM companies
            WHERE id = %s
        """, (company_id,))
        company = cur.fetchone()

        if form_type == "910":
            report = _build_910_report(cur, company_id, year, period)
        else:
            report = _build_200_report(cur, company_id, year, period)

        cur.execute("""
            SELECT * FROM accounting_filings
            WHERE company_id=%s AND form_type=%s AND report_year=%s AND report_period=%s
        """, (company_id, form_type, year, str(period)))
        filing = cur.fetchone()
        filing_events = []
        if filing:
            cur.execute("""
                SELECT * FROM accounting_filing_events
                WHERE filing_id=%s ORDER BY created_at DESC,id DESC LIMIT 20
            """, (filing["id"],))
            filing_events = cur.fetchall()

        return render_template(
            "accounting_report.html",
            report=report,
            company=company,
            selected_year=year,
            selected_period=str(period),
            filing=filing,
            filing_events=filing_events,
            isna_gateway_ready=bool(current_app.config.get("ISNA_GATEWAY_URL")),
        )
    finally:
        cur.close()
        pool.putconn(conn)




def _build_isna_draft_json(report, company, selected_year, selected_period):
    """
    Структурированный JSON-черновик Nika Business.
    Карта полей вынесена отдельно, чтобы после получения официальной
    JSON-схемы ИСНА заменить только адаптер, не меняя расчёты.
    """
    base = {
        "meta": {
            "system": "Nika Business",
            "format": "ISNA_DRAFT",
            "formCode": f"{report['form_type']}.00",
            "formVersion": report.get("form_version"),
            "formRevision": report.get("form_revision"),
            "year": int(selected_year),
            "period": str(selected_period),
            "generatedAt": now_kz().isoformat(),
        },
        "taxpayer": {
            "bin": (company or {}).get("bin") or "",
            "name": (company or {}).get("name") or "",
            "address": (company or {}).get("address") or "",
            "director": (company or {}).get("director") or "",
        },
        "period": {
            "label": report.get("period_label"),
            "dateFrom": report["date_from"].isoformat(),
            "dateTo": report["date_to"].isoformat(),
            "submitDue": report["submit_due"].isoformat(),
            "paymentDue": report["payment_due"].isoformat(),
        },
        "lines": [
            {
                "code": line["code"],
                "name": line["name"],
                "value": float(line.get("amount") or 0),
                "source": line.get("source") or "",
            }
            for line in report.get("official_lines", [])
        ],
    }

    if report["form_type"] == "910":
        base["details"] = {
            "income": float(report.get("income") or 0),
            "refunds": float(report.get("refunds") or 0),
            "taxableIncome": float(report.get("taxable_income") or 0),
            "rate": float(report.get("rate") or 0),
            "taxAmount": float(report.get("tax_amount") or 0),
            "months": report.get("months", []),
        }
    else:
        base["details"] = {
            "employeeCount": int(report.get("employee_count") or 0),
            "totals": report.get("totals", {}),
            "months": report.get("months", []),
            "employees": report.get("employees", []),
        }

    return base


def _filing_event(cur, filing_id, company_id, event_type, from_status,
                  to_status, details=None):
    cur.execute("""
        INSERT INTO accounting_filing_events (
            filing_id, company_id, user_id, event_type, from_status,
            to_status, details, created_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        filing_id, company_id, session.get("user_id"), event_type,
        from_status, to_status, json.dumps(details or {}, ensure_ascii=False),
        now_kz(),
    ))


def _filing_redirect(filing, message=None):
    suffix = (
        f"form_type={filing['form_type']}&year={filing['report_year']}"
        f"&period={filing['report_period']}"
    )
    if message:
        suffix += f"&filing_message={message}"
    return redirect(f"/accounting/report?{suffix}#isnaWorkflow")


@accounting_bp.route("/accounting/report/prepare", methods=["POST"])
def prepare_accounting_filing():
    if not session.get("user_id"):
        return redirect("/login")
    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    form_type = request.form.get("form_type", "").strip()
    period = request.form.get("period", "1").strip()
    try:
        year = int(request.form.get("year") or now_kz().year)
    except ValueError:
        return "Неверный год", 400
    if form_type not in {"200", "910"}:
        return "Неизвестная форма", 400

    conn = get_db(); cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur); _ensure_tax_tables(cur)
        cur.execute("SELECT id,name,bin,address,director FROM companies WHERE id=%s", (company_id,))
        company = cur.fetchone()
        report = (_build_910_report(cur, company_id, year, period)
                  if form_type == "910" else _build_200_report(cur, company_id, year, period))
        if not report.get("ready"):
            conn.rollback()
            return "Форма не прошла проверку готовности", 409
        payload = _build_isna_draft_json(report, company, year, period)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        cur.execute("""
            SELECT * FROM accounting_filings
            WHERE company_id=%s AND form_type=%s AND report_year=%s AND report_period=%s
            FOR UPDATE
        """, (company_id, form_type, year, period))
        existing = cur.fetchone()
        if existing and existing["status"] in {"sent", "accepted"}:
            conn.rollback()
            return "Эта форма уже отправлена; повторная отправка заблокирована", 409
        previous_status = existing["status"] if existing else None
        cur.execute("""
            INSERT INTO accounting_filings (
                company_id,user_id,form_type,report_year,report_period,
                form_version,form_revision,payload,payload_hash,status,prepared_at,updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'prepared',%s,%s)
            ON CONFLICT (company_id,form_type,report_year,report_period) DO UPDATE SET
                user_id=EXCLUDED.user_id, form_version=EXCLUDED.form_version,
                form_revision=EXCLUDED.form_revision, payload=EXCLUDED.payload,
                payload_hash=EXCLUDED.payload_hash, signature=NULL,
                certificate_subject=NULL, status='prepared', error_message=NULL,
                prepared_at=EXCLUDED.prepared_at, signed_at=NULL, updated_at=EXCLUDED.updated_at
            RETURNING *
        """, (company_id, session.get("user_id"), form_type, year, period,
              report.get("form_version"), report.get("form_revision"),
              canonical, payload_hash, now_kz(), now_kz()))
        filing = cur.fetchone()
        _filing_event(cur, filing["id"], company_id, "prepared", previous_status,
                      "prepared", {"payload_hash": payload_hash})
        conn.commit()
        return _filing_redirect(filing, "prepared")
    except Exception as exc:
        conn.rollback(); print("PREPARE FILING ERROR:", exc)
        return "Не удалось подготовить форму", 500
    finally:
        cur.close(); pool.putconn(conn)


@accounting_bp.route("/accounting/filings/<int:filing_id>/signature", methods=["POST"])
def save_accounting_filing_signature(filing_id):
    if not session.get("user_id"):
        return redirect("/login")
    company_id = _require_company()
    signature = (request.form.get("signature") or "").strip()
    subject = (request.form.get("certificate_subject") or "").strip()
    if len(signature) < 32:
        return "Подпись отсутствует или имеет неверный формат", 400
    conn = get_db(); cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("SELECT * FROM accounting_filings WHERE id=%s AND company_id=%s FOR UPDATE", (filing_id, company_id))
        filing = cur.fetchone()
        if not filing:
            return "Форма не найдена", 404
        if filing["status"] not in {"prepared", "signed", "failed"}:
            return "Форму нельзя подписать в текущем статусе", 409
        previous_status = filing["status"]
        cur.execute("""
            UPDATE accounting_filings SET signature=%s,certificate_subject=%s,
                status='signed',signed_at=%s,error_message=NULL,updated_at=%s
            WHERE id=%s RETURNING *
        """, (signature, subject or None, now_kz(), now_kz(), filing_id))
        filing = cur.fetchone()
        _filing_event(cur, filing_id, company_id, "signed", previous_status, "signed",
                      {"certificate_subject": subject})
        conn.commit()
        return _filing_redirect(filing, "signed")
    except Exception as exc:
        conn.rollback(); print("SIGN FILING ERROR:", exc)
        return "Не удалось сохранить подпись", 500
    finally:
        cur.close(); pool.putconn(conn)


@accounting_bp.route("/accounting/filings/<int:filing_id>/send", methods=["POST"])
def send_accounting_filing(filing_id):
    if not session.get("user_id"):
        return redirect("/login")
    company_id = _require_company()
    gateway_url = (current_app.config.get("ISNA_GATEWAY_URL") or "").strip()
    if not gateway_url:
        return "Шлюз ИСНА ещё не настроен. Укажите ISNA_GATEWAY_URL.", 503
    conn = get_db(); cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        cur.execute("SELECT * FROM accounting_filings WHERE id=%s AND company_id=%s FOR UPDATE", (filing_id, company_id))
        filing = cur.fetchone()
        if not filing:
            return "Форма не найдена", 404
        if filing["status"] != "signed" or not filing["signature"]:
            return "Сначала подпишите форму ЭЦП", 409
        envelope = json.dumps({
            "idempotencyKey": filing["payload_hash"],
            "document": filing["payload"],
            "signature": filing["signature"],
        }, ensure_ascii=False, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json", "Idempotency-Key": filing["payload_hash"]}
        token = current_app.config.get("ISNA_GATEWAY_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = urlrequest.urlopen(urlrequest.Request(gateway_url, data=envelope, headers=headers, method="POST"), timeout=30)
            response_data = json.loads(response.read().decode("utf-8") or "{}")
        except (urlerror.URLError, TimeoutError, ValueError) as exc:
            cur.execute("UPDATE accounting_filings SET status='failed',error_message=%s,updated_at=%s WHERE id=%s RETURNING *",
                        (str(exc), now_kz(), filing_id))
            failed = cur.fetchone()
            _filing_event(cur, filing_id, company_id, "send_failed", "signed", "failed", {"error": str(exc)})
            conn.commit()
            return _filing_redirect(failed, "failed")
        gateway_status = str(response_data.get("status") or "sent").lower()
        new_status = "accepted" if gateway_status == "accepted" else "sent"
        cur.execute("""
            UPDATE accounting_filings SET status=%s,external_id=%s,registration_number=%s,
                response_payload=%s,error_message=NULL,sent_at=%s,
                accepted_at=CASE WHEN %s='accepted' THEN %s ELSE accepted_at END,updated_at=%s
            WHERE id=%s RETURNING *
        """, (new_status, response_data.get("id"), response_data.get("registrationNumber"),
              json.dumps(response_data, ensure_ascii=False), now_kz(), new_status,
              now_kz(), now_kz(), filing_id))
        filing = cur.fetchone()
        _filing_event(cur, filing_id, company_id, "sent", "signed", new_status, response_data)
        conn.commit()
        return _filing_redirect(filing, new_status)
    except Exception as exc:
        conn.rollback(); print("SEND FILING ERROR:", exc)
        return "Не удалось отправить форму", 500
    finally:
        cur.close(); pool.putconn(conn)


@accounting_bp.route("/accounting/report/export-json")
def export_accounting_report_json():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    form_type = request.args.get("form_type", "910").strip()
    year = int(request.args.get("year") or now_kz().year)
    period = request.args.get("period", "1")

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        _ensure_tax_tables(cur)
        conn.commit()

        cur.execute("""
            SELECT id, name, bin, address, director
            FROM companies
            WHERE id = %s
        """, (company_id,))
        company = cur.fetchone()

        if form_type == "910":
            report = _build_910_report(cur, company_id, year, period)
        elif form_type == "200":
            report = _build_200_report(cur, company_id, year, period)
        else:
            return "Неизвестная форма", 400

        payload = _build_isna_draft_json(
            report, company, year, period
        )
        data = json.dumps(
            payload, ensure_ascii=False, indent=2, default=str
        ).encode("utf-8")
        stream = BytesIO(data)
        stream.seek(0)

        filename = f"{form_type}_{year}_{period}_isna_draft.json"
        return send_file(
            stream,
            as_attachment=True,
            download_name=filename,
            mimetype="application/json; charset=utf-8",
        )
    finally:
        cur.close()
        pool.putconn(conn)


@accounting_bp.route("/accounting/report/create-debt", methods=["POST"])
def create_report_debt():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _require_company()
    if not company_id:
        return "Активная компания не выбрана", 400

    form_type = request.form.get("form_type", "").strip()
    year = request.form.get("year", "").strip()
    period = request.form.get("period", "").strip()

    if form_type not in {"200", "910"}:
        return "Неизвестная форма", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        _ensure_tax_tables(cur)

        if form_type == "910":
            report = _build_910_report(cur, company_id, int(year), period)
            amount = report["tax_amount"]
            title = f"Налог по форме 910.00 — {report['period_label']}"
        else:
            report = _build_200_report(cur, company_id, int(year), period)
            amount = report["total_payments"]
            title = f"Платежи по форме 200.00 — {report['period_label']}"

        tax_key = f"report:{form_type}:{year}:{period}"
        cur.execute("""
            INSERT INTO accounting_debts (
                company_id, user_id, title, description,
                due_date, amount, status, created_at, updated_at, tax_key
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'debt', %s, %s, %s)
            ON CONFLICT (company_id, tax_key)
            WHERE tax_key IS NOT NULL
            DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                due_date = EXCLUDED.due_date,
                amount = EXCLUDED.amount,
                updated_at = EXCLUDED.updated_at
        """, (
            company_id,
            session.get("user_id"),
            title,
            f"Автоматически создано из черновика формы {form_type}.00",
            report["payment_due"],
            amount,
            now_kz(),
            now_kz(),
            tax_key,
        ))
        conn.commit()

        return redirect(
            f"/accounting/report?form_type={form_type}&year={year}&period={period}"
        )
    finally:
        cur.close()
        pool.putconn(conn)
