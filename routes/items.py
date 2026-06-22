from flask import Blueprint, render_template, request, redirect, jsonify
from models import get_db, pool
from werkzeug.utils import secure_filename
from flask import session
from datetime import datetime
from flask import jsonify
import json
import os
import uuid

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
    pool.putconn(conn)
    return render_template("items.html", items=items)

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
                company_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            request.form.get("is_marked") == "1",
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
                is_marked = %s
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
            request.form.get("ntin"),
            request.form.get("is_marked") == "1",
            item_id,
            session.get("company_id")
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

    cur.execute("""
        INSERT INTO categories
        (company_id, name, markup_percent)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (
        session.get("company_id"),
        data["name"],
        data.get("markup", 0)
    ))

    category_id = cur.fetchone()["id"]

    conn.commit()
    pool.putconn(conn)

    return jsonify({
        "id": category_id,
        "name": data["name"],
        "markup_percent": data.get("markup", 0)
    })
    
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
    
@items_bp.route("/api/barcode-info/<barcode>")
def barcode_info(barcode):

    import requests

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        SELECT *
        FROM items
        WHERE barcode = %s
    """, (barcode,))

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

        })

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
            quantity,
            company_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        bool(data.get("is_marked", False)),
        float(data.get("quantity") or 0),
        session.get("company_id")
    ))

    item_id = cur.fetchone()["id"]

    # если количество больше 0 — создаём приход в движении товара
    quantity = float(data.get("quantity") or 0)
    purchase_price = float(data.get("purchase_price") or 0)

    if quantity > 0:
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
    pool.putconn(conn)

    return jsonify({
        "success": True,
        "id": item_id
    })