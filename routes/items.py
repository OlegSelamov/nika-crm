from flask import Blueprint, render_template, request, redirect, jsonify
from models import get_db
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
    items = conn.execute("""
    SELECT 
        items.*,
        (SELECT image FROM item_images 
         WHERE item_id = items.id 
         LIMIT 1) as image
    FROM items
    WHERE items.company_id = ?
    """, (session.get("company_id"),)).fetchall()
    conn.close()
    return render_template("items.html", items=items)

@items_bp.route("/items/add", methods=["GET", "POST"])
def add_item():

    conn = get_db()

    if request.method == "POST":

        company_id = session.get("company_id")

        conn.execute("""
            INSERT INTO items 
            (
                name,
                category,
                unit,
                description,
                retail_price,
                wholesale_price,
                purchase_price,
                discount_percent,
                barcode,
                company_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["category"],
            request.form.get("unit"),
            request.form.get("description"),
            request.form.get("retail_price"),
            request.form.get("wholesale_price"),
            request.form.get("purchase_price"),
            request.form.get("discount_percent"),
            request.form.get("barcode"),
            company_id
        ))

        item_id = conn.execute("""
            SELECT last_insert_rowid()
        """).fetchone()[0]

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

                conn.execute("""
                    INSERT INTO item_images
                    (
                        item_id,
                        image
                    )
                    VALUES (?, ?)
                """, (
                    item_id,
                    image_path
                ))

        conn.commit()

        conn.close()

        return redirect("/items")

    # категории
    categories = conn.execute("""
        SELECT *
        FROM categories
        WHERE company_id = ?
        ORDER BY name
    """, (
        session.get("company_id"),
    )).fetchall()

    conn.close()

    return render_template(
        "item_form.html",
        categories=categories
    )
    
@items_bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id):
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            UPDATE items
            SET 
                name = ?,
                category = ?,
                unit = ?,
                description = ?,
                retail_price = ?,
                wholesale_price = ?,
                purchase_price = ?,
                discount_percent = ?,
                barcode = ?
            WHERE id = ? AND company_id = ?
        """, (
            request.form["name"],
            request.form["category"],
            request.form.get("unit"),
            request.form.get("description"),
            request.form.get("retail_price"),
            request.form.get("wholesale_price"),
            request.form.get("purchase_price"),
            request.form.get("discount_percent"),
            request.form.get("barcode"),
            item_id,
            session.get("company_id")
        ))

        conn.commit()
        conn.close()
        return redirect("/items")

    item = conn.execute(
        "SELECT * FROM items WHERE id = ? AND company_id = ?",
        (item_id, session.get("company_id"))
    ).fetchone()

    conn = get_db()

    categories = conn.execute("""
        SELECT *
        FROM categories
        WHERE company_id = ?
        ORDER BY name
    """, (
        session.get("company_id"),
    )).fetchall()

    conn.close()

    return render_template(
        "item_form.html",
        item=item,
        categories=categories
    )
    
@items_bp.route("/items/<int:item_id>/delete")
def delete_item(item_id):
    conn = get_db()

    conn.execute(
        "DELETE FROM items WHERE id = ? AND company_id = ?",
        (item_id, session.get("company_id"))
    )

    conn.commit()
    conn.close()

    return redirect("/items")
    
@items_bp.route("/api/items")
def api_items():
    conn = get_db()

    items = conn.execute("""
    SELECT 
        items.*,
        (SELECT image FROM item_images 
         WHERE item_id = items.id 
         LIMIT 1) as image
    FROM items
    WHERE items.company_id = ?
    """, (session.get("company_id"),)).fetchall()

    conn.close()

    return [dict(i) for i in items]
    
@items_bp.route("/add_category", methods=["POST"])
def add_category():
    data = request.json

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO categories
        (company_id, name, markup_percent)
        VALUES (?, ?, ?)
    """, (
        session.get("company_id"),
        data["name"],
        data.get("markup", 0)
    ))

    category_id = cur.lastrowid

    conn.commit()
    conn.close()

    return jsonify({
        "id": category_id,
        "name": data["name"],
        "markup_percent": data.get("markup", 0)
    })
    
@items_bp.route("/delete_category/<int:id>", methods=["POST"])
def delete_category(id):

    conn = get_db()

    conn.execute("""
        DELETE FROM categories
        WHERE id = ?
        AND company_id = ?
    """, (
        id,
        session.get("company_id")
    ))

    conn.commit()

    conn.close()

    return jsonify({"success": True})
    
@items_bp.route("/api/barcode-info/<barcode>")
def barcode_info(barcode):

    import requests

    db = get_db()

    # 🔥 СНАЧАЛА СВОЯ БАЗА
    item = db.execute(
        """
        SELECT *
        FROM items
        WHERE barcode=?
        """,
        (barcode,)
    ).fetchone()

    # ✅ нашли локально
    if item:

        return jsonify({

            "found": True,

            "local": True,

            "name": item["name"],

            "category": item["category"],

            "price": item["retail_price"],

            "image": item["image"]

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

                "barcode":
                    barcode

            })

    except Exception as e:

        print("NCT ERROR:", e)

    return jsonify({
        "found": False
    })