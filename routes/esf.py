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
from utils.timezone import now_kz


esf_bp = Blueprint("esf", __name__)
ESF_VERSION = "InvoiceV2"
MONEY = Decimal("0.01")


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
            prepared_at TIMESTAMP,
            signed_at TIMESTAMP,
            sent_at TIMESTAMP,
            accepted_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, sale_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_esf_documents_company_status
        ON esf_documents (company_id, status, updated_at DESC)
    """)
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
    return format(_money(value), "f")


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
        SELECT si.*, i.item_type
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
        products.append({
            "sale_item_id": item["id"],
            "catalog_tru_id": str(index),
            "description": item.get("name") or "Товар",
            "quantity": str(item.get("quantity") or 1),
            "price_with_tax": _decimal_text(item.get("price")),
            "tru_origin_code": "",
            "unit_code": "",
            "unit_nomenclature": "796" if (item.get("unit") or "").lower() in {"шт", "шт."} else "",
            "unit_label": item.get("unit") or "шт",
            "gtin_code": item.get("gtin") or "",
            "item_type": item.get("item_type") or "product",
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
        },
        "tax": {"nds_rate": "0"},
        "products": products,
    }


def _validation_errors(payload):
    errors = []
    invoice = payload.get("invoice") or {}
    seller = payload.get("seller") or {}
    customer = payload.get("customer") or {}
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
    if not products:
        errors.append("В продаже нет товаров или услуг.")
    for index, product in enumerate(products, 1):
        if not str(product.get("catalog_tru_id") or "").strip():
            errors.append(f"Строка {index}: укажите идентификатор ТРУ.")
        if str(product.get("tru_origin_code") or "") not in {"1", "2", "3", "4", "5", "6"}:
            errors.append(f"Строка {index}: выберите признак происхождения ТРУ (1–6).")
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
    if delivery.get("contract_num") or delivery.get("contract_date"):
        term = ET.SubElement(root, "deliveryTerm")
        _add(term, "contractDate", _date_text(delivery.get("contract_date")))
        _add(term, "contractNum", delivery.get("contract_num"))
        _add(term, "hasContract", "true")

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
        if nds_rate:
            _add(product_el, "ndsRate", str(nds_rate.quantize(Decimal("1"))), True)
        _add(product_el, "priceWithTax", _decimal_text(total_with_tax), True)
        _add(product_el, "priceWithoutTax", _decimal_text(total_without_tax), True)
        _add(product_el, "quantity", str(quantity.normalize()), True)
        _add(product_el, "truOriginCode", product.get("tru_origin_code"), True)
        _add(product_el, "turnoverSize", _decimal_text(total_without_tax), True)
        _add(product_el, "unitCode", product.get("unit_code"))
        _add(product_el, "unitNomenclature", product.get("unit_nomenclature"))
        _add(product_el, "unitPrice", _decimal_text(unit_without_tax))
        totals["nds"] += nds_amount
        totals["with_tax"] += total_with_tax
        totals["without_tax"] += total_without_tax

    _add(product_set, "totalExciseAmount", "0.00", True)
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
    _add(seller_el, "countryCode", seller.get("country_code") or "KZ")
    _add(seller_el, "iik", seller.get("iik"))
    _add(seller_el, "kbe", seller.get("kbe"))
    _add(seller_el, "name", seller.get("name"), True)
    _add(seller_el, "tin", seller.get("tin"), True)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _document_view(row, fallback_payload):
    payload = row.get("payload") if row else fallback_payload
    errors = _validation_errors(payload)
    return {
        "id": row.get("id") if row else None,
        "sale_id": row.get("sale_id") if row else None,
        "version": row.get("version") if row else ESF_VERSION,
        "status": row.get("status") if row else "new",
        "payload": payload,
        "payload_hash": row.get("payload_hash") if row else None,
        "signed_at": _json_value(row.get("signed_at")) if row else None,
        "registration_number": row.get("registration_number") if row else None,
        "validation_errors": errors,
        "can_sign": bool(row and row.get("invoice_xml") and not errors and row.get("status") in {"draft", "prepared", "signed", "failed"}),
        "can_send": bool(row and row.get("status") == "signed" and row.get("signature")),
        "send_available": False,
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
                signed_at=NULL,updated_at=EXCLUDED.updated_at
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

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_esf_schema(cur)
        cur.execute("SELECT * FROM esf_documents WHERE company_id=%s AND sale_id=%s FOR UPDATE", (company_id, sale_id))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Сначала сохраните черновик ЭСФ"}), 404
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
