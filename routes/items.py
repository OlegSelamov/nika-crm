from flask import Blueprint, render_template, request, redirect
from models import get_db
from werkzeug.utils import secure_filename
import os
import uuid

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
    """).fetchall()
    conn.close()
    return render_template("items.html", items=items)

@items_bp.route("/items/add", methods=["GET", "POST"])
def add_item():
    if request.method == "POST":
        conn = get_db()

        conn.execute("""
            INSERT INTO items 
            (name, category, description, retail_price, wholesale_price, purchase_price, discount_percent, barcode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["category"],
            request.form.get("description"),
            request.form.get("retail_price"),
            request.form.get("wholesale_price"),
            request.form.get("purchase_price"),
            request.form.get("discount_percent"),
            request.form.get("barcode")
        ))

        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        files = request.files.getlist("images")

        for file in files:
            if file and file.filename:

                filename = secure_filename(file.filename)
                ext = filename.split('.')[-1]

                unique_name = f"{uuid.uuid4()}.{ext}"

                save_path = os.path.join("static/uploads", unique_name)
                file.save(save_path)

                db_path = "/" + save_path.replace("\\", "/")

                conn.execute(
                    "INSERT INTO item_images (item_id, image) VALUES (?, ?)",
                    (item_id, db_path)
                )

        conn.commit()
        conn.close()

        return redirect("/items")

    return render_template("item_form.html")
    
@items_bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id):
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            UPDATE items
            SET 
                name = ?,
                category = ?,
                description = ?,
                retail_price = ?,
                wholesale_price = ?,
                purchase_price = ?,
                discount_percent = ?,
                barcode = ?
            WHERE id = ?
        """, (
            request.form["name"],
            request.form["category"],
            request.form.get("description"),
            request.form.get("retail_price"),
            request.form.get("wholesale_price"),
            request.form.get("purchase_price"),
            request.form.get("discount_percent"),
            request.form.get("barcode"),
            item_id
        ))

        conn.commit()
        conn.close()
        return redirect("/items")

    item = conn.execute(
        "SELECT * FROM items WHERE id = ?",
        (item_id,)
    ).fetchone()

    conn.close()

    return render_template("item_form.html", item=item)
    
@items_bp.route("/items/<int:item_id>/delete")
def delete_item(item_id):
    conn = get_db()

    conn.execute(
        "DELETE FROM items WHERE id = ?",
        (item_id,)
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
        (SELECT image FROM item_images WHERE item_id = items.id LIMIT 1) as image
    FROM items
    """).fetchall()
    conn.close()

    return [dict(i) for i in items]