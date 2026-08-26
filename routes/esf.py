"""Черновики ЭСФ, сформированные из продаж.

Модуль намеренно не хранит закрытые ключи ЭЦП. Подпись выполняется в
браузере через NCALayer, а сервер получает только результат подписи.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
import re
from xml.etree import ElementTree as ET

from flask import Blueprint, Response, jsonify, request, session

from models import get_db, pool
from services.esf_service import (
    EsfApiError,
    build_revoke_signable,
    close_session,
    configuration as esf_api_configuration,
    create_auth_ticket,
    create_signed_session,
    revoke_invoice,
    send_invoice,
)
from utils.timezone import now_kz


esf_bp = Blueprint("esf", __name__)
ESF_VERSION = "InvoiceV2"
MONEY = Decimal("0.01")
ESF_PROFILE_TYPES = {
    "ADMIN_ENTERPRISE",
    "USER",
    "ENTREPRENEUR",
    "ENTREPRENEUR_USER",
    "INDIVIDUAL",
}


def _ensure_esf_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS esf_documents (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            sale_id INTEGER NOT NULL,
            user_id INTEGER,
            version VARCHAR(30) NOT NULL DEFAULT 'InvoiceV2',
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            payload JSONB NOT NULL,
            invoice_xml TEXT,
            payload_hash VARCHAR(64),
            signature TEXT,
            x509_certificate TEXT,
            certificate_subject TEXT,
            external_id TEXT,
            registration_number TEXT,
            response_payload JSONB,
            error_message TEXT,
            api_environment VARCHAR(20),
            revoke_reason TEXT,
            revoke_signature TEXT,
            revoke_certificate TEXT,
            revoke_response JSONB,
            prepared_at TIMESTAMP,
            signed_at TIMESTAMP,
            sent_at TIMESTAMP,
            accepted_at TIMESTAMP,
            revoked_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, sale_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_esf_documents_company_status
        ON esf_documents (company_id, status, updated_at DESC)
    """)
    cur.execute("ALTER TABLE esf_documents ADD COLUMN IF NOT EXISTS api_environment VARCHAR(20)")
    cur.execute("ALTER TABLE esf_documents ADD COLUMN IF NOT EXISTS revoke_reason TEXT")
    cur.execute("ALTER TABLE esf_documents ADD COLUMN IF NOT EXISTS revoke_signature TEXT")
    cur.execute("ALTER TABLE esf_documents ADD COLUMN IF NOT EXISTS revoke_certificate TEXT")
    cur.execute("ALTER TABLE esf_documents ADD COLUMN IF NOT EXISTS revoke_response JSONB")
    cur.execute("ALTER TABLE esf_documents ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS esf_document_events (
            id SERIAL PRIMARY KEY,
            esf_document_id INTEGER NOT NULL REFERENCES esf_documents(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            event_type VARCHAR(40) NOT NULL,
            from_status VARCHAR(30),
            to_status VARCHAR(30) NOT NULL,
            details JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _number(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _decimal_text(value):
    """Serialize XML decimal in plain notation without insignificant zeros.

    ИС ЭСФ отклоняет значения вроде 1000.00 и 0.00 как содержащие
    незначащие нули. При этом XML Schema decimal не допускает экспоненту.
    """
    text = format(_money(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _number_text(value):
    """Plain XML decimal for quantity: no exponent and no trailing zeros."""
    try:
        text = format(Decimal(str(value or 0)), "f")
    except (InvalidOperation, ValueError, TypeError):
        return "0"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _date_text(value):
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:10], pattern).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return text


def _api_auth_payload(data, seller_tin):
    iin = str(data.get("iin") or "").strip()
    password = str(data.get("password") or "")
    signed_ticket = str(data.get("signed_auth_ticket") or "").strip()
    profile_type = str(data.get("profile_type") or "ADMIN_ENTERPRISE").strip().upper()
    if not re.fullmatch(r"\d{12}", iin):
        raise ValueError("Укажите ИИН пользователя ИС ЭСФ — ровно 12 цифр.")
    if not password:
        raise ValueError("Введите пароль пользователя ИС ЭСФ.")
    if len(password) > 256:
        raise ValueError("Пароль пользователя ИС ЭСФ слишком длинный.")
    if len(signed_ticket) < 200 or "Signature" not in signed_ticket:
        raise ValueError("Тикет авторизации не подписан через NCALayer.")
    if profile_type not in ESF_PROFILE_TYPES:
        raise ValueError("Выбран неподдерживаемый профиль ИС ЭСФ.")
    tin = str(seller_tin or "").strip()
    if not re.fullmatch(r"\d{12}", tin):
        raise ValueError("В реквизитах поставщика должен быть указан БИН/ИИН из 12 цифр.")
    return {
        "tin": tin,
        "iin": iin,
        "password": password,
        "signed_auth_ticket": signed_ticket,
        "profile_type": profile_type,
    }


def _api_error_json(error):
    payload = {"success": False, "error": str(error)}
    if getattr(error, "details", None):
        payload["details"] = error.details
    return jsonify(payload), 502



_ESF_UNIT_NOMENCLATURE = {
    # МКЕИ / классификатор единиц измерения, используемый ИС ЭСФ.
    "услуга": "5114", "услуги": "5114", "одна услуга": "5114",
    "шт": "796", "шт.": "796", "штука": "796", "штук": "796",
    "кг": "166", "килограмм": "166", "килограммы": "166",
    "г": "163", "гр": "163", "грамм": "163",
    "л": "112", "л.": "112", "литр": "112", "литры": "112",
    "мл": "111", "миллилитр": "111",
    "м": "006", "метр": "006", "метры": "006",
    "м2": "055", "м²": "055", "кв.м": "055", "кв. м": "055",
    "м3": "113", "м³": "113", "куб.м": "113", "куб. м": "113",
    "час": "356", "ч": "356", "часов": "356",
    "сут": "359", "сутки": "359", "день": "359", "дней": "359",
    "мес": "362", "месяц": "362", "месяцев": "362",
    "год": "366", "лет": "366",
    "пара": "715", "пар": "715",
}


def _esf_unit_nomenclature(unit, item_type=None):
    """Return the classifier code used by INVOICEV2 unitNomenclature.

    For services, Kazakhstan's measurement classifier contains the dedicated
    unit 'Одна услуга' with code 5114. Use it for the Nika catalog values
    'услуга'/'услуги' and as the default when a service has no unit set.
    The field itself remains editable in the ESF form.
    """
    raw = str(unit or "").strip().lower().replace("ё", "е")
    raw = re.sub(r"\s+", " ", raw)
    if raw in {"услуга", "услуги", "одна услуга"}:
        return "5114"
    if not raw and str(item_type or "").strip().lower() == "service":
        return "5114"
    return _ESF_UNIT_NOMENCLATURE.get(raw, "")

def _invoice_number(sale):
    candidate = str(sale.get("sale_number") or "")
    digits = "".join(re.findall(r"\d+", candidate))
    return (digits or str(sale["id"]))[:30]


def _source_data(cur, company_id, sale_id):
    cur.execute(
        "SELECT * FROM sales WHERE id=%s AND company_id=%s",
        (sale_id, company_id),
    )
    sale = cur.fetchone()
    if not sale:
        return None

    cur.execute("SELECT * FROM companies WHERE id=%s", (company_id,))
    company = cur.fetchone() or {}
    cur.execute(
        "SELECT * FROM clients WHERE id=%s AND company_id=%s",
        (sale.get("client_id"), company_id),
    )
    client = cur.fetchone() or {}
    cur.execute("""
        SELECT si.*, i.item_type,
               i.ntin AS catalog_ntin, i.gtin AS catalog_gtin, i.unit AS catalog_unit
        FROM sale_items si
        LEFT JOIN items i ON i.id=si.item_id AND i.company_id=%s
        WHERE si.sale_id=%s
        ORDER BY si.id
    """, (company_id, sale_id))
    items = cur.fetchall() or []
    return sale, company, client, items


def _initial_payload(source):
    sale, company, client, items = source
    date = _date_text(sale.get("created_at") or now_kz())
    products = []
    for index, item in enumerate(items, 1):
        item_type = item.get("item_type") or "product"
        unit_value = item.get("unit") or item.get("catalog_unit")
        # В XSD INVOICEV2 историческое имя поля осталось gtinCode,
        # но в актуальном бланке ИС ЭСФ это графа «Код товара».
        # Для товаров с 2026 года сюда передаётся код НКТ NTIN/XTIN.
        # Берём снимок из sale_items, а если его нет — актуальный NTIN из каталога.
        product_code = (item.get("ntin") or item.get("catalog_ntin") or
                        item.get("gtin") or item.get("catalog_gtin") or "")
        products.append({
            "sale_item_id": item["id"],
            # Поле catalogTruId обязательно в API ИС ЭСФ. Для обычных ТРУ,
            # которые не ведутся на Виртуальном складе, используется значение «1».
            # Для товара ВС пользователь может заменить его на реальный составной код ГСВС.
            "catalog_tru_id": "1",
            "description": item.get("name") or "Товар",
            "quantity": str(item.get("quantity") or 1),
            "price_with_tax": _decimal_text(item.get("price")),
            # Для работ/услуг признак происхождения по правилам ИС ЭСФ = 6.
            "tru_origin_code": "6" if item_type == "service" else "",
            # В INVOICEV2 unitCode = код ТН ВЭД, а unitNomenclature =
            # код единицы измерения по классификатору (796=шт, 166=кг и т.д.).
            "unit_code": "",
            "unit_nomenclature": _esf_unit_nomenclature(unit_value, item_type),
            "unit_label": unit_value or ("услуга" if item_type == "service" else "шт"),
            "gtin_code": "" if item_type == "service" else product_code,
            "item_type": item_type,
        })

    return {
        "invoice": {
            "num": _invoice_number(sale),
            "date": date,
            "turnover_date": date,
            "invoice_type": "ORDINARY_INVOICE",
            "operator_fullname": company.get("director") or "",
        },
        "seller": {
            "name": company.get("name") or "",
            "tin": company.get("bin") or "",
            "address": company.get("address") or "",
            "country_code": "KZ",
            "bank": company.get("bank") or "",
            "bik": company.get("bik") or "",
            "iik": company.get("iik") or "",
            "kbe": company.get("kbe") or "",
            "certificate_series": "",
            "certificate_num": "",
        },
        "customer": {
            "name": client.get("company_name") or client.get("full_name") or "",
            "tin": client.get("iin") or "",
            "address": client.get("address") or "",
            "country_code": "KZ",
        },
        "delivery": {
            "document_num": sale.get("sale_number") or str(sale["id"]),
            "document_date": date,
            "contract_num": client.get("contract_number") or "",
            "contract_date": _date_text(client.get("contract_date")),
            # С 10.07.2026 поле E28 «Способ расчета» обязательно.
            # Только полностью наличная продажа = CASH; карта/Kaspi/смешанная = NON_CASH.
            "payment_form": (
                "CASH"
                if (sale.get("sale_type") or "cash") == "cash"
                and _number(sale.get("card_amount")) <= 0
                and _number(sale.get("kaspi_amount")) <= 0
                else "NON_CASH"
            ),
        },
        "tax": {"nds_rate": "0"},
        "products": products,
    }


def _normalize_payload(payload):
    """Normalize fields that are deterministic from the Nika item type.

    For services/works IS ESF uses origin code 6. They are not Virtual Warehouse
    stock lots, so Nika must not send an arbitrary composite GSVS code entered in
    an old draft. The generic TRU identifier is 1.
    """
    if not isinstance(payload, dict):
        return payload
    normalized = json.loads(json.dumps(payload, ensure_ascii=False))
    for product in normalized.get("products") or []:
        item_type = str(product.get("item_type") or "").strip().lower()
        # catalogTruId обязателен в XML, но не должен быть обязательным реквизитом
        # карточки товара в Nika. Если отдельный ID не задан, используем «1» —
        # стандартное значение для ТРУ, не ведущихся на Виртуальном складе.
        if not str(product.get("catalog_tru_id") or "").strip():
            product["catalog_tru_id"] = "1"
        if item_type == "service":
            product["catalog_tru_id"] = "1"
            product["tru_origin_code"] = "6"
            product["gtin_code"] = ""
        if not str(product.get("unit_nomenclature") or "").strip():
            product["unit_nomenclature"] = _esf_unit_nomenclature(
                product.get("unit_label"), item_type
            )
    return normalized


def _validation_errors(payload):
    errors = []
    invoice = payload.get("invoice") or {}
    seller = payload.get("seller") or {}
    customer = payload.get("customer") or {}
    delivery = payload.get("delivery") or {}
    products = payload.get("products") or []

    required = (
        (invoice.get("num"), "Укажите номер ЭСФ."),
        (invoice.get("date"), "Укажите дату выписки ЭСФ."),
        (invoice.get("turnover_date"), "Укажите дату оборота."),
        (seller.get("name"), "Укажите наименование поставщика."),
        (seller.get("tin"), "Укажите ИИН/БИН поставщика."),
        (customer.get("name"), "Укажите получателя."),
        (customer.get("country_code"), "Укажите страну получателя."),
    )
    errors.extend(message for value, message in required if not str(value or "").strip())
    if not re.fullmatch(r"\d{1,30}", str(invoice.get("num") or "")):
        errors.append("Номер ЭСФ должен содержать только 1–30 цифр.")
    if not re.fullmatch(r"\d{8,20}", str(seller.get("tin") or "")):
        errors.append("ИИН/БИН поставщика должен содержать 8–20 цифр.")
    customer_tin = str(customer.get("tin") or "")
    if customer_tin and not re.fullmatch(r"\d{8,20}", customer_tin):
        errors.append("ИИН/БИН получателя должен содержать 8–20 цифр.")
    if str(delivery.get("payment_form") or "") not in {"CASH", "NON_CASH"}:
        errors.append("Укажите способ расчета: наличный или безналичный.")
    if not products:
        errors.append("В продаже нет товаров или услуг.")
    for index, product in enumerate(products, 1):
        # ID ТРУ не требуем хранить в карточке товара: перед формированием XML
        # пустое значение нормализуется в «1». Для товара Виртуального склада
        # пользователь указывает реальный составной код ГСВС в самой форме ЭСФ.
        origin_code = str(product.get("tru_origin_code") or "")
        if origin_code not in {"1", "2", "3", "4", "5", "6"}:
            errors.append(f"Строка {index}: выберите признак происхождения ТРУ (1–6).")
        product_code = str(product.get("gtin_code") or "").strip()
        item_type = str(product.get("item_type") or "").strip().lower()
        # NTIN/XTIN пока не делаем обязательным для каждого товара.
        # Если код есть в карточке/черновике — передаём его в ИС ЭСФ;
        # если поля нет — элемент gtinCode просто не формируется.
        # Валидацию формата выполняем только для заполненного значения.
        if item_type != "service" and origin_code != "6" and product_code:
            if not re.fullmatch(r"(?:02\d{11}|004\d{10})", product_code):
                errors.append(
                    f"Строка {index}: код товара должен быть NTIN (02 + 11 цифр) "
                    "или XTIN (004 + 10 цифр), всего 13 цифр."
                )
        unit_nom = str(product.get("unit_nomenclature") or "").strip()
        # Для товаров единица измерения обязательна. Для работ/услуг (код 6)
        # Nika по умолчанию ставит 5114 «Одна услуга».
        if origin_code in {"1", "2", "3", "4", "5"} and not unit_nom:
            errors.append(f"Строка {index}: укажите единицу измерения ЭСФ.")
        if unit_nom and not re.fullmatch(r"[A-Za-z0-9]{1,10}", unit_nom):
            errors.append(f"Строка {index}: некорректный код единицы измерения ЭСФ.")
        if _number(product.get("quantity")) <= 0:
            errors.append(f"Строка {index}: количество должно быть больше нуля.")
    return errors


def _add(parent, name, value, required=False):
    if value in (None, "") and not required:
        return None
    child = ET.SubElement(parent, name)
    child.text = str(value or "")
    return child


def _build_invoice_xml(payload):
    payload = _normalize_payload(payload)
    ET.register_namespace("v2", "v2.esf")
    root = ET.Element("{v2.esf}invoice", {"xmlns:a": "abstractInvoice.esf"})
    invoice = payload.get("invoice") or {}
    seller = payload.get("seller") or {}
    customer = payload.get("customer") or {}
    delivery = payload.get("delivery") or {}
    products = payload.get("products") or []
    try:
        nds_rate = Decimal(str((payload.get("tax") or {}).get("nds_rate") or 0))
    except InvalidOperation:
        nds_rate = Decimal("0")

    _add(root, "date", _date_text(invoice.get("date")), True)
    _add(root, "invoiceType", invoice.get("invoice_type") or "ORDINARY_INVOICE", True)
    _add(root, "num", invoice.get("num"), True)
    _add(root, "operatorFullname", invoice.get("operator_fullname"), True)
    _add(root, "turnoverDate", _date_text(invoice.get("turnover_date")), True)

    customers = ET.SubElement(root, "customers")
    customer_el = ET.SubElement(customers, "customer")
    _add(customer_el, "address", customer.get("address"))
    _add(customer_el, "countryCode", customer.get("country_code") or "KZ", True)
    _add(customer_el, "name", customer.get("name"), True)
    _add(customer_el, "tin", customer.get("tin"))

    _add(root, "deliveryDocDate", _date_text(delivery.get("document_date")))
    _add(root, "deliveryDocNum", delivery.get("document_num"))

    # В актуальном INVOICEV2 раздел E (deliveryTerm) содержит обязательный
    # paymentForm. После обновления ИС ЭСФ 10.07.2026 допустимы только
    # CASH (наличный) и NON_CASH (безналичный).
    has_contract = bool(delivery.get("contract_num") or delivery.get("contract_date"))
    term = ET.SubElement(root, "deliveryTerm")
    if has_contract:
        _add(term, "contractDate", _date_text(delivery.get("contract_date")))
        _add(term, "contractNum", delivery.get("contract_num"))
    _add(term, "hasContract", "true" if has_contract else "false", True)
    _add(term, "paymentForm", delivery.get("payment_form"), True)

    product_set = ET.SubElement(root, "productSet")
    _add(product_set, "currencyCode", "KZT", True)
    products_el = ET.SubElement(product_set, "products")
    totals = {key: Decimal("0") for key in ("nds", "with_tax", "without_tax")}
    divisor = Decimal("1") + (nds_rate / Decimal("100"))
    for product in products:
        quantity = _number(product.get("quantity"))
        unit_with_tax = _money(product.get("price_with_tax"))
        total_with_tax = (quantity * unit_with_tax).quantize(MONEY, rounding=ROUND_HALF_UP)
        total_without_tax = (total_with_tax / divisor).quantize(MONEY, rounding=ROUND_HALF_UP) if nds_rate else total_with_tax
        nds_amount = total_with_tax - total_without_tax
        unit_without_tax = (unit_with_tax / divisor).quantize(MONEY, rounding=ROUND_HALF_UP) if nds_rate else unit_with_tax

        product_el = ET.SubElement(products_el, "product")
        _add(product_el, "catalogTruId", product.get("catalog_tru_id"), True)
        _add(product_el, "description", product.get("description"))
        _add(product_el, "gtinCode", product.get("gtin_code"))
        _add(product_el, "ndsAmount", _decimal_text(nds_amount), True)
        # Для неплательщика НДС ставка в бланке означает «Без НДС».
        # В API INVOICEV2 это не числовая ставка 0%: элемент ndsRate
        # должен отсутствовать. Если передать <ndsRate>0</ndsRate>,
        # боевая ИС ЭСФ возвращает ФЛК invoiceV2.product.ndsRate.exists.
        # Числовой ndsRate отправляем только для реальной ставки НДС > 0.
        if nds_rate > 0:
            _add(product_el, "ndsRate", _number_text(nds_rate), True)
        _add(product_el, "priceWithTax", _decimal_text(total_with_tax), True)
        _add(product_el, "priceWithoutTax", _decimal_text(total_without_tax), True)
        _add(product_el, "quantity", _number_text(quantity), True)
        _add(product_el, "truOriginCode", product.get("tru_origin_code"), True)
        _add(product_el, "turnoverSize", _decimal_text(total_without_tax), True)
        _add(product_el, "unitCode", product.get("unit_code"))
        _add(product_el, "unitNomenclature", product.get("unit_nomenclature"))
        _add(product_el, "unitPrice", _decimal_text(unit_without_tax))
        totals["nds"] += nds_amount
        totals["with_tax"] += total_with_tax
        totals["without_tax"] += total_without_tax

    _add(product_set, "totalExciseAmount", "0", True)
    _add(product_set, "totalNdsAmount", _decimal_text(totals["nds"]), True)
    _add(product_set, "totalPriceWithTax", _decimal_text(totals["with_tax"]), True)
    _add(product_set, "totalPriceWithoutTax", _decimal_text(totals["without_tax"]), True)
    _add(product_set, "totalTurnoverSize", _decimal_text(totals["without_tax"]), True)

    sellers = ET.SubElement(root, "sellers")
    seller_el = ET.SubElement(sellers, "seller")
    _add(seller_el, "address", seller.get("address"))
    _add(seller_el, "bank", seller.get("bank"))
    _add(seller_el, "bik", seller.get("bik"))
    _add(seller_el, "certificateNum", seller.get("certificate_num"))
    _add(seller_el, "certificateSeries", seller.get("certificate_series"))
    # countryCode поставщика заполняется только для нерезидента.
    # Для казахстанского ИП/ТОО элемент передавать нельзя.
    seller_country = str(seller.get("country_code") or "KZ").strip().upper()
    if seller_country and seller_country != "KZ":
        _add(seller_el, "countryCode", seller_country)
    _add(seller_el, "iik", seller.get("iik"))
    _add(seller_el, "kbe", seller.get("kbe"))
    _add(seller_el, "name", seller.get("name"), True)
    _add(seller_el, "tin", seller.get("tin"), True)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _document_view(row, fallback_payload):
    payload = _normalize_payload(row.get("payload") if row else fallback_payload)
    errors = _validation_errors(payload)
    api_config = esf_api_configuration()
    status = row.get("status") if row else "new"
    has_external_id = bool(row and row.get("external_id"))
    return {
        "id": row.get("id") if row else None,
        "sale_id": row.get("sale_id") if row else None,
        "version": row.get("version") if row else ESF_VERSION,
        "status": status,
        "payload": payload,
        "payload_hash": row.get("payload_hash") if row else None,
        "signed_at": _json_value(row.get("signed_at")) if row else None,
        "sent_at": _json_value(row.get("sent_at")) if row else None,
        "revoked_at": _json_value(row.get("revoked_at")) if row else None,
        "external_id": row.get("external_id") if row else None,
        "registration_number": row.get("registration_number") if row else None,
        "error_message": row.get("error_message") if row else None,
        "revoke_reason": row.get("revoke_reason") if row else None,
        # До фактической отправки показываем текущую настроенную среду API.
        # Это важно после неудачной попытки на test: старая запись не должна
        # заставлять интерфейс продолжать показывать "ТЕСТОВАЯ ИС ЭСФ",
        # когда сервер уже переключён на production.
        "api_environment": (
            row.get("api_environment")
            if row and has_external_id and row.get("api_environment")
            else api_config.environment
        ),
        "validation_errors": errors,
        "can_sign": bool(row and row.get("invoice_xml") and not errors and status in {"draft", "prepared", "signed", "failed"} and not has_external_id),
        "can_send": bool(row and status in {"signed", "failed"} and row.get("signature") and row.get("x509_certificate") and not errors and not has_external_id),
        "can_revoke": bool(row and has_external_id and status in {"sent", "accepted", "revoke_failed"}),
        "send_available": True,
    }


@esf_bp.route("/api/sales/<int:sale_id>/esf", methods=["GET"])
def get_sale_esf(sale_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_esf_schema(cur)
        source = _source_data(cur, company_id, sale_id)
        if not source:
            return jsonify({"success": False, "error": "Продажа не найдена"}), 404
        cur.execute("SELECT * FROM esf_documents WHERE company_id=%s AND sale_id=%s", (company_id, sale_id))
        row = cur.fetchone()
        return jsonify({"success": True, "document": _document_view(row, _initial_payload(source))})
    finally:
        conn.commit()
        cur.close()
        pool.putconn(conn)


@esf_bp.route("/api/sales/<int:sale_id>/esf/draft", methods=["POST"])
def save_sale_esf_draft(sale_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401
    payload = (request.get_json(silent=True) or {}).get("payload")
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Не переданы данные ЭСФ"}), 400

    payload = _normalize_payload(payload)
    invoice_xml = _build_invoice_xml(payload)
    payload_hash = sha256(invoice_xml.encode("utf-8")).hexdigest()
    errors = _validation_errors(payload)
    status = "draft" if errors else "prepared"
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_esf_schema(cur)
        if not _source_data(cur, company_id, sale_id):
            return jsonify({"success": False, "error": "Продажа не найдена"}), 404
        cur.execute("SELECT id,status FROM esf_documents WHERE company_id=%s AND sale_id=%s", (company_id, sale_id))
        previous = cur.fetchone()
        if previous and previous.get("status") in {
            "sending", "sent", "accepted", "revoke_pending", "revoked", "revoke_failed"
        }:
            return jsonify({
                "success": False,
                "error": "Отправленную ЭСФ нельзя перезаписать. Для неё доступны только просмотр статуса и отзыв.",
            }), 409
        cur.execute("""
            INSERT INTO esf_documents (
                company_id,sale_id,user_id,version,status,payload,invoice_xml,
                payload_hash,prepared_at,updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (company_id,sale_id) DO UPDATE SET
                user_id=EXCLUDED.user_id,version=EXCLUDED.version,status=EXCLUDED.status,
                payload=EXCLUDED.payload,invoice_xml=EXCLUDED.invoice_xml,
                payload_hash=EXCLUDED.payload_hash,signature=NULL,x509_certificate=NULL,
                certificate_subject=NULL,error_message=NULL,prepared_at=EXCLUDED.prepared_at,
                signed_at=NULL,external_id=NULL,registration_number=NULL,response_payload=NULL,
                api_environment=NULL,revoke_reason=NULL,revoke_signature=NULL,
                revoke_certificate=NULL,revoke_response=NULL,sent_at=NULL,accepted_at=NULL,
                revoked_at=NULL,updated_at=EXCLUDED.updated_at
            RETURNING *
        """, (company_id, sale_id, session.get("user_id"), ESF_VERSION, status,
              json.dumps(payload, ensure_ascii=False), invoice_xml, payload_hash,
              now_kz(), now_kz()))
        row = cur.fetchone()
        cur.execute("""
            INSERT INTO esf_document_events (
                esf_document_id,company_id,user_id,event_type,from_status,to_status,details,created_at
            ) VALUES (%s,%s,%s,'draft_saved',%s,%s,%s,%s)
        """, (row["id"], company_id, session.get("user_id"),
              previous.get("status") if previous else None, status,
              json.dumps({"payload_hash": payload_hash, "validation_errors": errors}, ensure_ascii=False), now_kz()))
        conn.commit()
        return jsonify({
            "success": True,
            "document": _document_view(row, payload),
            "invoice_xml": invoice_xml,
            "message": "Черновик сохранён" if errors else "ЭСФ подготовлена к подписи",
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.rollback()
        cur.close()
        pool.putconn(conn)


@esf_bp.route("/api/sales/<int:sale_id>/esf/signature", methods=["POST"])
def save_sale_esf_signature(sale_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401
    data = request.get_json(silent=True) or {}
    signature = str(data.get("signature") or "").strip()
    payload_hash = str(data.get("payload_hash") or "").strip()
    certificate = str(data.get("certificate") or "").strip()
    subject = str(data.get("certificate_subject") or "").strip()
    if len(signature) < 64:
        return jsonify({"success": False, "error": "NCALayer не вернул подпись"}), 400
    if len(signature) > 400:
        return jsonify({
            "success": False,
            "error": "Получен CMS-контейнер вместо подписи ИС ЭСФ. Обновите страницу и подпишите документ заново.",
        }), 400
    if len(certificate) < 100:
        return jsonify({
            "success": False,
            "error": "NCALayer не вернул сертификат подписи. Повторите подпись обновлённой кнопкой.",
        }), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_esf_schema(cur)
        cur.execute("SELECT * FROM esf_documents WHERE company_id=%s AND sale_id=%s FOR UPDATE", (company_id, sale_id))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Сначала сохраните черновик ЭСФ"}), 404
        if row.get("external_id") or row.get("status") in {
            "sending", "sent", "accepted", "revoke_pending", "revoked", "revoke_failed"
        }:
            return jsonify({"success": False, "error": "ЭСФ уже передана в ИС ЭСФ и не может быть подписана заново"}), 409
        errors = _validation_errors(row["payload"])
        if errors:
            return jsonify({"success": False, "error": "Заполните обязательные поля", "validation_errors": errors}), 409
        if not payload_hash or payload_hash != row.get("payload_hash"):
            return jsonify({"success": False, "error": "Черновик изменился. Сохраните и подпишите его заново"}), 409
        cur.execute("""
            UPDATE esf_documents SET signature=%s,x509_certificate=%s,
                certificate_subject=%s,status='signed',signed_at=%s,updated_at=%s,
                error_message=NULL WHERE id=%s RETURNING *
        """, (signature, certificate or None, subject or None, now_kz(), now_kz(), row["id"]))
        signed = cur.fetchone()
        cur.execute("""
            INSERT INTO esf_document_events (
                esf_document_id,company_id,user_id,event_type,from_status,to_status,details,created_at
            ) VALUES (%s,%s,%s,'signed',%s,'signed',%s,%s)
        """, (row["id"], company_id, session.get("user_id"), row["status"],
              json.dumps({"payload_hash": payload_hash, "certificate_subject": subject}, ensure_ascii=False), now_kz()))
        conn.commit()
        return jsonify({
            "success": True,
            "document": _document_view(signed, signed["payload"]),
            "message": "ЭСФ подписана и сохранена. В ИС ЭСФ пока не отправлена.",
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.rollback()
        cur.close()
        pool.putconn(conn)


@esf_bp.route("/api/sales/<int:sale_id>/esf/auth-ticket", methods=["POST"])
def get_sale_esf_auth_ticket(sale_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401
    data = request.get_json(silent=True) or {}
    iin = str(data.get("iin") or "").strip()
    if not re.fullmatch(r"\d{12}", iin):
        return jsonify({"success": False, "error": "Укажите ИИН пользователя ИС ЭСФ — ровно 12 цифр."}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_esf_schema(cur)
        cur.execute("SELECT id FROM esf_documents WHERE company_id=%s AND sale_id=%s", (company_id, sale_id))
        if not cur.fetchone():
            return jsonify({"success": False, "error": "Сначала сохраните и подпишите ЭСФ"}), 404
        conn.commit()
        try:
            ticket = create_auth_ticket(iin, ttl_minutes=15)
        except EsfApiError as error:
            return _api_error_json(error)
        return jsonify({
            "success": True,
            "auth_ticket_xml": ticket,
            "api_environment": esf_api_configuration().environment,
        })
    finally:
        conn.rollback()
        cur.close()
        pool.putconn(conn)


@esf_bp.route("/api/sales/<int:sale_id>/esf/auth-check", methods=["POST"])
def check_sale_esf_auth(sale_id):
    """Open and immediately close an IS ESF API session without sending a document."""
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    data = request.get_json(silent=True) or {}
    conn = get_db()
    cur = conn.cursor()
    api_session_id = None
    api_auth = None
    try:
        _ensure_esf_schema(cur)
        cur.execute(
            "SELECT * FROM esf_documents WHERE company_id=%s AND sale_id=%s",
            (company_id, sale_id),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Сначала сохраните ЭСФ"}), 404

        try:
            api_auth = _api_auth_payload(
                data,
                (row.get("payload") or {}).get("seller", {}).get("tin"),
            )
        except ValueError as error:
            return jsonify({"success": False, "error": str(error)}), 400

        config = esf_api_configuration()
        try:
            api_session_id = create_signed_session(**api_auth)
        except EsfApiError as error:
            return _api_error_json(error)

        return jsonify({
            "success": True,
            "api_environment": config.environment,
            "message": (
                "Авторизация в боевой ИС ЭСФ успешна. API-сессия открыта и закрыта; "
                "ЭСФ не отправлялась."
                if config.environment == "production"
                else
                "Авторизация в тестовой ИС ЭСФ успешна. API-сессия открыта и закрыта; "
                "ЭСФ не отправлялась."
            ),
        })
    finally:
        close_session(
            api_session_id,
            iin=(api_auth or {}).get("iin"),
            password=(api_auth or {}).get("password"),
        )
        conn.rollback()
        cur.close()
        pool.putconn(conn)


@esf_bp.route("/api/sales/<int:sale_id>/esf/send", methods=["POST"])
def send_sale_esf(sale_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401
    data = request.get_json(silent=True) or {}
    conn = get_db()
    cur = conn.cursor()
    api_session_id = None
    api_auth = None
    try:
        _ensure_esf_schema(cur)
        cur.execute(
            "SELECT * FROM esf_documents WHERE company_id=%s AND sale_id=%s FOR UPDATE",
            (company_id, sale_id),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "ЭСФ не найдена"}), 404
        if row.get("external_id"):
            return jsonify({"success": False, "error": "ЭСФ уже передана в ИС ЭСФ"}), 409
        if row.get("status") not in {"signed", "failed"} or not row.get("signature"):
            return jsonify({"success": False, "error": "Сначала подпишите ЭСФ через NCALayer"}), 409
        if not row.get("x509_certificate"):
            return jsonify({"success": False, "error": "В подписи отсутствует сертификат. Подпишите ЭСФ заново"}), 409
        try:
            auth = _api_auth_payload(data, (row.get("payload") or {}).get("seller", {}).get("tin"))
            api_auth = auth
        except ValueError as error:
            return jsonify({"success": False, "error": str(error)}), 400

        previous_status = row["status"]
        config = esf_api_configuration()
        cur.execute(
            "UPDATE esf_documents SET status='sending',api_environment=%s,error_message=NULL,updated_at=%s WHERE id=%s",
            (config.environment, now_kz(), row["id"]),
        )
        conn.commit()

        try:
            api_session_id = create_signed_session(**auth)
            result = send_invoice(
                session_id=api_session_id,
                invoice_xml=row["invoice_xml"],
                signature=row["signature"],
                certificate=row["x509_certificate"],
                version=row.get("version") or ESF_VERSION,
            )
        except EsfApiError as error:
            error_text = str(error)
            if error.details:
                error_text = f"{error_text} {'; '.join(error.details)}"
            cur.execute(
                "UPDATE esf_documents SET status='failed',error_message=%s,response_payload=%s,updated_at=%s WHERE id=%s",
                (
                    error_text[:4000],
                    json.dumps({"error": str(error), "details": error.details}, ensure_ascii=False),
                    now_kz(),
                    row["id"],
                ),
            )
            cur.execute("""
                INSERT INTO esf_document_events (
                    esf_document_id,company_id,user_id,event_type,from_status,to_status,details,created_at
                ) VALUES (%s,%s,%s,'send_failed',%s,'failed',%s,%s)
            """, (
                row["id"], company_id, session.get("user_id"), previous_status,
                json.dumps({"error": str(error), "details": error.details}, ensure_ascii=False), now_kz(),
            ))
            conn.commit()
            return _api_error_json(error)
        finally:
            close_session(
                api_session_id,
                iin=(api_auth or {}).get("iin"),
                password=(api_auth or {}).get("password"),
            )
            api_session_id = None

        external_id = str(result.get("id") or "").strip()
        if not external_id:
            error = EsfApiError("ИС ЭСФ приняла запрос, но не вернула ID документа. Проверьте журнал ИС ЭСФ.")
            cur.execute(
                "UPDATE esf_documents SET status='failed',error_message=%s,response_payload=%s,updated_at=%s WHERE id=%s",
                (str(error), json.dumps(result, ensure_ascii=False), now_kz(), row["id"]),
            )
            conn.commit()
            return _api_error_json(error)
        cur.execute("""
            UPDATE esf_documents SET status='sent',external_id=%s,response_payload=%s,
                sent_at=%s,updated_at=%s,error_message=NULL WHERE id=%s RETURNING *
        """, (
            external_id,
            json.dumps(result, ensure_ascii=False),
            now_kz(), now_kz(), row["id"],
        ))
        sent = cur.fetchone()
        cur.execute("""
            INSERT INTO esf_document_events (
                esf_document_id,company_id,user_id,event_type,from_status,to_status,details,created_at
            ) VALUES (%s,%s,%s,'sent',%s,'sent',%s,%s)
        """, (
            row["id"], company_id, session.get("user_id"), previous_status,
            json.dumps({"external_id": external_id, "api_environment": config.environment}, ensure_ascii=False),
            now_kz(),
        ))
        conn.commit()
        return jsonify({
            "success": True,
            "document": _document_view(sent, sent["payload"]),
            "message": "ЭСФ передана в очередь ИС ЭСФ. ID документа сохранён в Nika.",
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        close_session(
            api_session_id,
            iin=(api_auth or {}).get("iin"),
            password=(api_auth or {}).get("password"),
        )
        conn.rollback()
        cur.close()
        pool.putconn(conn)


@esf_bp.route("/api/sales/<int:sale_id>/esf/revoke/prepare", methods=["POST"])
def prepare_sale_esf_revoke(sale_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401
    reason = str((request.get_json(silent=True) or {}).get("reason") or "").strip()
    if len(reason) < 3:
        return jsonify({"success": False, "error": "Укажите причину отзыва — минимум 3 символа."}), 400
    if len(reason) > 1000:
        return jsonify({"success": False, "error": "Причина отзыва не должна превышать 1000 символов."}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_esf_schema(cur)
        cur.execute(
            "SELECT * FROM esf_documents WHERE company_id=%s AND sale_id=%s",
            (company_id, sale_id),
        )
        row = cur.fetchone()
        if not row or not row.get("external_id"):
            return jsonify({"success": False, "error": "Сначала отправьте ЭСФ и получите её ID"}), 409
        if row.get("status") not in {"sent", "accepted", "revoke_failed"}:
            return jsonify({"success": False, "error": "Текущий статус ЭСФ не позволяет оформить отзыв"}), 409
        return jsonify({
            "success": True,
            "signable_xml": build_revoke_signable(row["external_id"], reason),
            "external_id": row["external_id"],
            "reason": reason,
        })
    finally:
        conn.commit()
        cur.close()
        pool.putconn(conn)


@esf_bp.route("/api/sales/<int:sale_id>/esf/revoke", methods=["POST"])
def revoke_sale_esf(sale_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()
    revoke_signature = str(data.get("revoke_signature") or "").strip()
    revoke_certificate = str(data.get("revoke_certificate") or "").strip()
    if len(reason) < 3 or len(reason) > 1000:
        return jsonify({"success": False, "error": "Укажите корректную причину отзыва."}), 400
    if len(revoke_signature) < 64 or len(revoke_signature) > 400 or len(revoke_certificate) < 100:
        return jsonify({"success": False, "error": "NCALayer не вернул подпись и сертификат для отзыва."}), 400

    conn = get_db()
    cur = conn.cursor()
    api_session_id = None
    api_auth = None
    try:
        _ensure_esf_schema(cur)
        cur.execute(
            "SELECT * FROM esf_documents WHERE company_id=%s AND sale_id=%s FOR UPDATE",
            (company_id, sale_id),
        )
        row = cur.fetchone()
        if not row or not row.get("external_id"):
            return jsonify({"success": False, "error": "Отправленная ЭСФ не найдена"}), 404
        if row.get("status") not in {"sent", "accepted", "revoke_failed"}:
            return jsonify({"success": False, "error": "Текущий статус ЭСФ не позволяет оформить отзыв"}), 409
        try:
            auth = _api_auth_payload(data, (row.get("payload") or {}).get("seller", {}).get("tin"))
            api_auth = auth
        except ValueError as error:
            return jsonify({"success": False, "error": str(error)}), 400

        previous_status = row["status"]
        config = esf_api_configuration()
        document_environment = str(row.get("api_environment") or "").strip().lower()
        if document_environment and document_environment != config.environment:
            return jsonify({
                "success": False,
                "error": (
                    f"Эта ЭСФ была отправлена в среду {document_environment}, "
                    f"а Nika сейчас подключена к {config.environment}. "
                    "Переключите среду перед отзывом документа."
                ),
            }), 409
        cur.execute(
            "UPDATE esf_documents SET status='revoking',revoke_reason=%s,error_message=NULL,updated_at=%s WHERE id=%s",
            (reason, now_kz(), row["id"]),
        )
        conn.commit()
        try:
            api_session_id = create_signed_session(**auth)
            result = revoke_invoice(
                session_id=api_session_id,
                invoice_id=row["external_id"],
                reason=reason,
                signature=revoke_signature,
                certificate=revoke_certificate,
            )
        except EsfApiError as error:
            error_text = str(error)
            if error.details:
                error_text = f"{error_text} {'; '.join(error.details)}"
            cur.execute("""
                UPDATE esf_documents SET status='revoke_failed',error_message=%s,
                    revoke_response=%s,updated_at=%s WHERE id=%s
            """, (
                error_text[:4000],
                json.dumps({"error": str(error), "details": error.details}, ensure_ascii=False),
                now_kz(), row["id"],
            ))
            cur.execute("""
                INSERT INTO esf_document_events (
                    esf_document_id,company_id,user_id,event_type,from_status,to_status,details,created_at
                ) VALUES (%s,%s,%s,'revoke_failed',%s,'revoke_failed',%s,%s)
            """, (
                row["id"], company_id, session.get("user_id"), previous_status,
                json.dumps({"error": str(error), "details": error.details}, ensure_ascii=False), now_kz(),
            ))
            conn.commit()
            return _api_error_json(error)
        finally:
            close_session(
                api_session_id,
                iin=(api_auth or {}).get("iin"),
                password=(api_auth or {}).get("password"),
            )
            api_session_id = None

        upstream_status = result.get("status") or ""
        next_status = "revoke_pending" if upstream_status == "WAITING_CUSTOMER_REVOKE_CONFIRMATION" else "revoked"
        cur.execute("""
            UPDATE esf_documents SET status=%s,registration_number=COALESCE(NULLIF(%s,''),registration_number),
                revoke_reason=%s,revoke_signature=%s,revoke_certificate=%s,revoke_response=%s,
                revoked_at=%s,api_environment=%s,updated_at=%s,error_message=NULL
            WHERE id=%s RETURNING *
        """, (
            next_status, result.get("registration_number") or "", reason,
            revoke_signature, revoke_certificate, json.dumps(result, ensure_ascii=False),
            now_kz() if next_status == "revoked" else None,
            config.environment, now_kz(), row["id"],
        ))
        revoked = cur.fetchone()
        cur.execute("""
            INSERT INTO esf_document_events (
                esf_document_id,company_id,user_id,event_type,from_status,to_status,details,created_at
            ) VALUES (%s,%s,%s,'revoke_requested',%s,%s,%s,%s)
        """, (
            row["id"], company_id, session.get("user_id"), previous_status, next_status,
            json.dumps({"upstream_status": upstream_status, "reason": reason}, ensure_ascii=False), now_kz(),
        ))
        conn.commit()
        message = (
            "Отзыв отправлен. Ожидается подтверждение получателя."
            if next_status == "revoke_pending"
            else "ЭСФ успешно отозвана в ИС ЭСФ."
        )
        return jsonify({
            "success": True,
            "document": _document_view(revoked, revoked["payload"]),
            "message": message,
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        close_session(
            api_session_id,
            iin=(api_auth or {}).get("iin"),
            password=(api_auth or {}).get("password"),
        )
        conn.rollback()
        cur.close()
        pool.putconn(conn)


@esf_bp.route("/api/sales/<int:sale_id>/esf/xml", methods=["GET"])
def download_sale_esf_xml(sale_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_esf_schema(cur)
        cur.execute("SELECT invoice_xml FROM esf_documents WHERE company_id=%s AND sale_id=%s", (company_id, sale_id))
        row = cur.fetchone()
        if not row or not row.get("invoice_xml"):
            return jsonify({"success": False, "error": "Черновик ЭСФ не найден"}), 404
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?>\n' + row["invoice_xml"],
            content_type="application/xml; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="esf-sale-{sale_id}.xml"'},
        )
    finally:
        conn.commit()
        cur.close()
        pool.putconn(conn)
