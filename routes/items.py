from flask import Blueprint, render_template, request, redirect, jsonify, send_file
from models import get_db, pool
from werkzeug.utils import secure_filename
from flask import session
from datetime import datetime
from flask import jsonify
import json
import os
import uuid
from io import BytesIO
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

UPLOAD_DIR = os.path.join(
    "static",
    "uploads",
    "items"
)

os.makedirs(UPLOAD_DIR, exist_ok=True)

items_bp = Blueprint("items", __name__)


@items_bp.route("/items")
def items():
    conn = get_db()
    
    cur = conn.cursor()
    
    cur.execute("""
    SELECT 
        items.*,
        (SELECT image FROM item_images 
         WHERE item_id = items.id 
         LIMIT 1) as image
    FROM items
    WHERE items.company_id = %s
    """, (session.get("company_id"),))
    items = cur.fetchall()

    cur.execute("""
        SELECT *
        FROM categories
        WHERE company_id = %s
        ORDER BY name
    """, (session.get("company_id"),))
    categories = cur.fetchall()

    pool.putconn(conn)
    return render_template("items.html", items=items, categories=categories)

@items_bp.route("/items/add", methods=["GET", "POST"])
def add_item():

    conn = get_db()
    
    cur = conn.cursor()

    if request.method == "POST":

        company_id = session.get("company_id")

        cur.execute("""
            INSERT INTO items (
                name,
                category,
                unit,
                description,
                retail_price,
                wholesale_price,
                purchase_price,
                discount_percent,
                barcode,
                gtin,
                ntin,
                is_marked,
                item_type,
                service_sale_mode,
                company_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            request.form["name"],
            request.form["category"],
            request.form.get("unit"),
            request.form.get("description"),
            float(request.form.get("retail_price") or 0),
            float(request.form.get("wholesale_price") or 0),
            float(request.form.get("purchase_price") or 0),
            int(request.form.get("discount_percent") or 0),
            request.form.get("barcode"),
            request.form.get("gtin"),
            request.form.get("ntin"),
            request.form.get("is_marked") == "1" if request.form.get("item_type", "product") == "product" else False,
            request.form.get("item_type", "product"),
            (request.form.get("service_sale_mode") or "order") if request.form.get("item_type", "product") == "service" else None,
            company_id
        ))

        item_id = cur.fetchone()["id"]

        # 🔥 загрузка картинок

        images = request.files.getlist("images")

        for image in images:

            if image and image.filename:

                filename = secure_filename(image.filename)

                filename = (
                    f"{uuid.uuid4().hex}_{filename}"
                )

                save_path = os.path.join(
                    UPLOAD_DIR,
                    filename
                )

                image.save(save_path)

                image_path = (
                    "/" + save_path.replace("\\", "/")
                )

                cur.execute("""
                    INSERT INTO item_images
                    (
                        item_id,
                        image
                    )
                    VALUES (%s, %s)
                """, (
                    item_id,
                    image_path
                ))

        conn.commit()

        pool.putconn(conn)

        return redirect("/items")

    # категории
    cur.execute("""
        SELECT *
        FROM categories
        WHERE company_id = %s
        ORDER BY name
    """, (
        session.get("company_id"),
    ))
    
    categories = cur.fetchall()

    pool.putconn(conn)

    return render_template(
        "item_form.html",
        categories=categories
    )
    
@items_bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id):
    conn = get_db()
    
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute("""
            UPDATE items
            SET 
                name = %s,
                category = %s,
                unit = %s,
                description = %s,
                retail_price = %s,
                wholesale_price = %s,
                purchase_price = %s,
                discount_percent = %s,
                barcode = %s,
                gtin = %s,
                ntin = %s,
                is_marked = %s,
                item_type = %s,
                service_sale_mode = %s
            WHERE id = %s AND company_id = %s
        """, (
            request.form["name"],
            request.form["category"],
            request.form.get("unit"),
            request.form.get("description"),
            float(request.form.get("retail_price") or 0),
            float(request.form.get("wholesale_price") or 0),
            float(request.form.get("purchase_price") or 0),
            int(request.form.get("discount_percent") or 0),
            request.form.get("barcode"),
            request.form.get("gtin"),
            request.form.get("ntin") if request.form.get("item_type", "product") == "product" else "",
            request.form.get("is_marked") == "1" if request.form.get("item_type", "product") == "product" else False,
            request.form.get("item_type", "product"),
            (request.form.get("service_sale_mode") or "order") if request.form.get("item_type", "product") == "service" else None,
            item_id,
            session.get("company_id")
        ))
        
        # Новое изображение при редактировании
        images = request.files.getlist("images")
        new_images = [
            image for image in images
            if image and image.filename
        ]

        if new_images:
            # Получаем старые изображения
            cur.execute("""
                SELECT image
                FROM item_images
                WHERE item_id = %s
            """, (item_id,))

            old_images = cur.fetchall()

            # Удаляем старые записи из БД
            cur.execute("""
                DELETE FROM item_images
                WHERE item_id = %s
            """, (item_id,))

            # Удаляем старые файлы
            for old_image in old_images:
                old_path = old_image["image"]

                if old_path:
                    file_path = old_path.lstrip("/")

                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass

            # Сохраняем новое изображение
            for image in new_images:
                filename = secure_filename(image.filename)

                filename = f"{uuid.uuid4().hex}_{filename}"

                save_path = os.path.join(
                    UPLOAD_DIR,
                    filename
                )

                image.save(save_path)

                image_path = "/" + save_path.replace("\\", "/")

                cur.execute("""
                    INSERT INTO item_images (
                        item_id,
                        image
                    )
                    VALUES (%s, %s)
                """, (
                    item_id,
                    image_path
                ))

        conn.commit()
        pool.putconn(conn)
        return redirect("/items")

    cur.execute(
        "SELECT * FROM items WHERE id = %s AND company_id = %s",
        (item_id, session.get("company_id"))
    )

    item = cur.fetchone()

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM categories
        WHERE company_id = %s
        ORDER BY name
    """, (
        session.get("company_id"),
    ))

    categories = cur.fetchall()

    pool.putconn(conn)

    return render_template(
        "item_form.html",
        item=item,
        categories=categories
    )
    
@items_bp.route("/items/<int:item_id>/delete")
def delete_item(item_id):
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM items WHERE id = %s AND company_id = %s",
        (item_id, session.get("company_id"))
    )

    conn.commit()
    pool.putconn(conn)

    return redirect("/items")
    
@items_bp.route("/api/items")
def api_items():
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
    SELECT 
        items.*,
        (SELECT image FROM item_images 
         WHERE item_id = items.id 
         LIMIT 1) as image
    FROM items
    WHERE items.company_id = %s
    """, (session.get("company_id"),))
    
    items = cur.fetchall()

    pool.putconn(conn)

    return [dict(i) for i in items]
    
@items_bp.route("/add_category", methods=["POST"])
def add_category():
    data = request.json

    conn = get_db()
    
    cur = conn.cursor()

    category_type = data.get("category_type", "product")
    if category_type not in ("product", "service"):
        category_type = "product"

    markup_percent = data.get("markup", 0) if category_type == "product" else 0

    cur.execute("""
        INSERT INTO categories
        (company_id, name, markup_percent, category_type)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, markup_percent, category_type
    """, (
        session.get("company_id"),
        data["name"],
        markup_percent,
        category_type
    ))

    category = cur.fetchone()

    conn.commit()
    pool.putconn(conn)

    return jsonify(dict(category))
    
@items_bp.route("/delete_category/<int:id>", methods=["POST"])
def delete_category(id):

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM categories
        WHERE id = %s
        AND company_id = %s
    """, (
        id,
        session.get("company_id")
    ))

    conn.commit()

    pool.putconn(conn)

    return jsonify({"success": True})
    
@items_bp.route("/edit_category/<int:id>", methods=["POST"])
def edit_category(id):
    data = request.json

    conn = get_db()
    cur = conn.cursor()

    category_type = data.get("category_type", "product")
    if category_type not in ("product", "service"):
        category_type = "product"

    markup_percent = data.get("markup", 0) if category_type == "product" else 0

    cur.execute("""
        UPDATE categories
        SET name = %s,
            markup_percent = %s,
            category_type = %s
        WHERE id = %s
          AND company_id = %s
        RETURNING id, name, markup_percent, category_type
    """, (
        data["name"],
        markup_percent,
        category_type,
        id,
        session.get("company_id")
    ))

    category = cur.fetchone()

    conn.commit()
    pool.putconn(conn)

    return jsonify(dict(category))
    
@items_bp.route("/api/barcode-info/<barcode>")
def barcode_info(barcode):

    import requests

    db = get_db()
    cur = db.cursor()

    item_type = request.args.get("item_type", "product")

    if item_type == "service":
        cur.execute("""
            SELECT *
            FROM items
            WHERE barcode = %s
              AND company_id = %s
              AND item_type = 'service'
        """, (
            barcode,
            session.get("company_id")
        ))
    else:
        cur.execute("""
            SELECT *
            FROM items
            WHERE barcode = %s
              AND company_id = %s
              AND COALESCE(item_type, 'product') = 'product'
        """, (
            barcode,
            session.get("company_id")
        ))

    item = cur.fetchone()

    # ✅ нашли локально
    if item:

        return jsonify({

            "found": True,

            "local": True,

            "name": item["name"],

            "category": item["category"],

            "price": item["retail_price"],
            
            "gtin": item.get("gtin"),
            
            "ntin": item.get("ntin"),
            
            "is_marked": item.get("is_marked"),
            "item_type": item.get("item_type") or "product",

        })

    if item_type == "service":
        pool.putconn(db)
        return jsonify({
            "found": False
        })

    pool.putconn(db)

    # 🌍 NATIONAL CATALOG
    try:

        url = (
            "https://e-catalog.gov.kz/"
            "api/integration/ofd/"
            f"search_ofd/?tin={barcode}"
        )

        TOKEN = os.getenv("NCT_API_TOKEN")
        
        print("TOKEN =", TOKEN[:30] if TOKEN else "NONE")

        headers = {
            "Authorization": f"JWT {TOKEN}"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        data = response.json()

        print("FULL DATA =", data)

        # 🔥 ЕСЛИ НАШЛИ
        if data:

            # 🔥 если results
            if "results" in data:

                if len(data["results"]) > 0:
                    product = data["results"][0]
                else:
                    product = {}

            # 🔥 если data
            elif "data" in data:

                product = data["data"]

            # 🔥 если список
            elif isinstance(data, list):

                product = data[0]

            # 🔥 обычный объект
            else:

                product = data

            return jsonify({

                "found": True,

                "external": True,

                "name":
                    product.get("name_ru", ""),
                    
                "measure":
                    product.get("measure", ""),

                "gtin":
                    product.get("gtin", ""),

                "ntin":
                    product.get("ntin_code", ""),
                    
                "is_marked":
                    product.get(
                        "is_markedeac",
                        False
                    ),

                "barcode":
                    barcode

            })

    except Exception as e:

        print("NCT ERROR:", e)

    return jsonify({
        "found": False
    })
    
@items_bp.route("/api/items/create", methods=["POST"])
def api_create_item():
    data = request.json

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO items (
            name,
            category,
            unit,
            type,
            description,
            retail_price,
            purchase_price,
            wholesale_price,
            discount_percent,
            barcode,
            gtin,
            ntin,
            is_marked,
            item_type,
            quantity,
            company_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        data.get("name", ""),
        data.get("category", ""),
        data.get("unit", "шт"),
        data.get("type", "piece"),
        data.get("description", ""),
        float(data.get("retail_price") or 0),
        float(data.get("purchase_price") or 0),
        float(data.get("wholesale_price") or 0),
        int(data.get("discount_percent") or 0),
        data.get("barcode", ""),
        data.get("gtin", ""),
        data.get("ntin", ""),
        bool(data.get("is_marked", False)) if data.get("item_type", "product") == "product" else False,
        data.get("item_type", "product"),
        float(data.get("quantity") or 0) if data.get("item_type", "product") == "product" else 0,
        session.get("company_id")
    ))

    item_id = cur.fetchone()["id"]

    # если количество больше 0 — создаём приход в движении товара
    quantity = float(data.get("quantity") or 0)
    purchase_price = float(data.get("purchase_price") or 0)

    item_type = data.get("item_type", "product")

    if quantity > 0 and item_type == "product":
        cur.execute("""
            INSERT INTO stock_movements (
                company_id,
                item_id,
                movement_type,
                quantity,
                price,
                total,
                comment,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session.get("company_id"),
            item_id,
            "income",
            quantity,
            purchase_price,
            quantity * purchase_price,
            "Первичный остаток при создании товара",
            datetime.now()
        ))

    conn.commit()

    cur.execute("""
        SELECT *
        FROM items
        WHERE id = %s
          AND company_id = %s
    """, (item_id, session.get("company_id")))

    item = cur.fetchone()
    pool.putconn(conn)

    return jsonify({
        "success": True,
        "item": dict(item)
    })

# ================== ИМПОРТ / ЭКСПОРТ КАТАЛОГА ==================

_CATALOG_HEADERS = [
    "Название", "Тип", "Категория", "Ед. изм.", "Штрихкод",
    "GTIN", "NTIN", "Закупочная цена", "Оптовая цена",
    "Розничная цена", "Скидка %", "Описание", "Количество"
]

_CATALOG_ALIASES = {
    "название": "name", "наименование": "name", "товар": "name",
    "тип": "item_type", "тип позиции": "item_type",
    "категория": "category",
    "ед. изм.": "unit", "ед изм": "unit", "единица измерения": "unit",
    "штрихкод": "barcode", "barcode": "barcode", "ean": "barcode",
    "gtin": "gtin", "ntin": "ntin",
    "закупочная цена": "purchase_price", "закуп": "purchase_price",
    "оптовая цена": "wholesale_price", "опт": "wholesale_price",
    "розничная цена": "retail_price", "цена": "retail_price",
    "скидка %": "discount_percent", "скидка": "discount_percent",
    "описание": "description", "количество": "quantity", "остаток": "quantity",
}


def _catalog_number(value, default=0):
    if value in (None, ""):
        return default
    try:
        normalized = str(value).strip().replace(" ", "").replace(",", ".")
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return default


def _catalog_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _style_excel_sheet(ws):
    header_fill = PatternFill("solid", fgColor="252B3A")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    widths = [34, 14, 24, 13, 20, 18, 18, 18, 18, 18, 12, 40, 14]
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + index)].width = width
    ws.auto_filter.ref = ws.dimensions


@items_bp.route("/items/export.xlsx")
def export_items_xlsx():
    company_id = session.get("company_id")
    if not company_id:
        return "Компания не выбрана", 403

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT name, item_type, category, unit, barcode, gtin, ntin,
                   purchase_price, wholesale_price, retail_price,
                   discount_percent, description, quantity
            FROM items
            WHERE company_id = %s
            ORDER BY COALESCE(item_type, 'product'), category, name
        """, (company_id,))
        rows = cur.fetchall()
    finally:
        pool.putconn(conn)

    wb = Workbook()
    ws = wb.active
    ws.title = "Каталог"
    ws.append(_CATALOG_HEADERS)

    for row in rows:
        ws.append([
            row.get("name") or "",
            "Услуга" if (row.get("item_type") or "product") == "service" else "Товар",
            row.get("category") or "",
            row.get("unit") or "",
            row.get("barcode") or "",
            row.get("gtin") or "",
            row.get("ntin") or "",
            row.get("purchase_price") or 0,
            row.get("wholesale_price") or 0,
            row.get("retail_price") or 0,
            row.get("discount_percent") or 0,
            row.get("description") or "",
            row.get("quantity") or 0,
        ])

    _style_excel_sheet(ws)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"nika_catalog_company_{company_id}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@items_bp.route("/items/import-template.xlsx")
def items_import_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "Каталог"
    ws.append(_CATALOG_HEADERS)
    ws.append([
        "Масло моторное 5W-30", "Товар", "Масла", "шт",
        "4870000000000", "", "", 12000, 0, 15500, 0,
        "Пример товара. Эту строку можно удалить.", 10
    ])
    ws.append([
        "Замена масла", "Услуга", "Автосервис", "услуга",
        "", "", "", 0, 0, 5000, 0,
        "Пример услуги. Эту строку можно удалить.", 0
    ])
    _style_excel_sheet(ws)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="nika_catalog_import_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@items_bp.route("/items/import", methods=["POST"])
def import_items_xlsx():
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "message": "Компания не выбрана"}), 403

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"success": False, "message": "Выберите Excel-файл"}), 400
    if not upload.filename.lower().endswith(".xlsx"):
        return jsonify({"success": False, "message": "Поддерживается формат .xlsx"}), 400

    duplicate_mode = request.form.get("duplicate_mode", "skip")
    if duplicate_mode not in ("skip", "update"):
        duplicate_mode = "skip"

    try:
        wb = load_workbook(upload, read_only=True, data_only=True)
        ws = wb.active
    except Exception:
        return jsonify({"success": False, "message": "Не удалось открыть Excel-файл"}), 400

    raw_headers = [_catalog_text(cell.value).lower() for cell in ws[1]]
    header_map = {}
    for column_index, header in enumerate(raw_headers, start=1):
        field = _CATALOG_ALIASES.get(header)
        if field:
            header_map[field] = column_index

    if "name" not in header_map:
        return jsonify({
            "success": False,
            "message": "В файле нет обязательной колонки «Название»"
        }), 400

    def value(row, field):
        column = header_map.get(field)
        return row[column - 1] if column else None

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
    conn = get_db()
    try:
        cur = conn.cursor()
        for excel_row, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            name = _catalog_text(value(row, "name"))
            if not name:
                continue

            try:
                raw_type = _catalog_text(value(row, "item_type")).lower()
                item_type = "service" if raw_type in ("услуга", "service", "работа") else "product"
                category = _catalog_text(value(row, "category")) or ("Услуги" if item_type == "service" else "Без категории")
                barcode = _catalog_text(value(row, "barcode"))
                gtin = _catalog_text(value(row, "gtin"))
                ntin = _catalog_text(value(row, "ntin"))
                unit = _catalog_text(value(row, "unit")) or ("услуга" if item_type == "service" else "шт")
                purchase_price = _catalog_number(value(row, "purchase_price"))
                wholesale_price = _catalog_number(value(row, "wholesale_price"))
                retail_price = _catalog_number(value(row, "retail_price"))
                discount_percent = int(_catalog_number(value(row, "discount_percent")))
                description = _catalog_text(value(row, "description"))
                quantity = _catalog_number(value(row, "quantity")) if item_type == "product" else Decimal("0")

                cur.execute("""
                    INSERT INTO categories (company_id, name, markup_percent, category_type)
                    SELECT %s, %s, 0, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM categories
                        WHERE company_id = %s AND LOWER(name) = LOWER(%s)
                              AND category_type = %s
                    )
                """, (company_id, category, item_type, company_id, category, item_type))

                existing = None
                if barcode:
                    cur.execute("""
                        SELECT id FROM items
                        WHERE company_id = %s AND barcode = %s
                              AND COALESCE(item_type, 'product') = %s
                        LIMIT 1
                    """, (company_id, barcode, item_type))
                    existing = cur.fetchone()

                if not existing:
                    cur.execute("""
                        SELECT id FROM items
                        WHERE company_id = %s AND LOWER(name) = LOWER(%s)
                              AND COALESCE(item_type, 'product') = %s
                        LIMIT 1
                    """, (company_id, name, item_type))
                    existing = cur.fetchone()

                if existing and duplicate_mode == "skip":
                    stats["skipped"] += 1
                    continue

                if existing:
                    cur.execute("""
                        UPDATE items SET
                            name=%s, category=%s, unit=%s, description=%s,
                            retail_price=%s, wholesale_price=%s, purchase_price=%s,
                            discount_percent=%s, barcode=%s, gtin=%s, ntin=%s,
                            item_type=%s, quantity=%s,
                            is_marked=CASE WHEN %s='service' THEN FALSE ELSE COALESCE(is_marked, FALSE) END
                        WHERE id=%s AND company_id=%s
                    """, (
                        name, category, unit, description, retail_price,
                        wholesale_price, purchase_price, discount_percent,
                        barcode, gtin, ntin, item_type, quantity,
                        item_type, existing["id"], company_id
                    ))
                    stats["updated"] += 1
                else:
                    cur.execute("""
                        INSERT INTO items (
                            name, category, unit, description, retail_price,
                            wholesale_price, purchase_price, discount_percent,
                            barcode, gtin, ntin, is_marked, item_type,
                            service_sale_mode, quantity, company_id
                        ) VALUES (
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,%s,%s,%s,%s
                        )
                    """, (
                        name, category, unit, description, retail_price,
                        wholesale_price, purchase_price, discount_percent,
                        barcode, gtin, ntin, item_type,
                        "order" if item_type == "service" else None,
                        quantity, company_id
                    ))
                    stats["created"] += 1
            except Exception as row_error:
                stats["errors"].append({"row": excel_row, "message": str(row_error)[:180]})
                if len(stats["errors"]) >= 50:
                    break

        conn.commit()
        return jsonify({"success": True, **stats})
    except Exception as error:
        conn.rollback()
        return jsonify({"success": False, "message": str(error)}), 500
    finally:
        pool.putconn(conn)
