from flask import Blueprint, render_template, request, redirect
from flask import session
from models import get_db
from datetime import datetime
from werkzeug.utils import secure_filename
import os

UPLOAD_DIR = os.path.join("static", "uploads", "clients")
COMMENT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "comments")

# создаём папки если их нет
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(COMMENT_UPLOAD_DIR, exist_ok=True)

clients_bp = Blueprint("clients", __name__)


@clients_bp.route("/clients")
def clients():
    conn = get_db()

    search = request.args.get("search", "").strip()

    if search:
        clients = conn.execute("""
            SELECT * FROM clients
            WHERE full_name LIKE ? AND company_id = ?
            ORDER BY id DESC
        """, (f"%{search}%", session.get("company_id"))).fetchall()
    else:
        clients = conn.execute("""
            SELECT * FROM clients
            WHERE company_id = ?
            ORDER BY id DESC
        """, (session.get("company_id"),)).fetchall()

    conn.close()

    return render_template("clients.html", clients=clients)


@clients_bp.route("/clients/add", methods=["GET", "POST"])
def add_client():
    if request.method == "POST":
        full_name = request.form["full_name"]
        phone = request.form.get("phone", "")
        iin = request.form.get("iin", "")
        company_name = request.form.get("company_name", "")
        status = request.form.get("status", "Новый")
        category = request.form.get("category", "")
        payment = request.form.get("payment", "Не оплачено")
        comment = request.form.get("comment", "")
        address = request.form.get("address", "")

        photo_path = ""
        comment_photo_paths = []

        photo = request.files.get("photo")
        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            save_path = os.path.join(UPLOAD_DIR, filename)
            photo.save(save_path)
            photo_path = "/" + save_path.replace("\\", "/")

        comment_photos = request.files.getlist("comment_photos")
        for file in comment_photos:
            if file and file.filename:
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                save_path = os.path.join(COMMENT_UPLOAD_DIR, filename)
                file.save(save_path)
                comment_photo_paths.append("/" + save_path.replace("\\", "/"))

        conn = get_db()
        
        print("CLIENT SAVE COMPANY:", session.get("company_id"))
        
        conn.execute(
            """
            INSERT INTO clients (
                full_name, phone, iin, company_name, status, category,
                payment, comment, address, photo, comment_photos, created_at, company_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                full_name,
                phone,
                iin,
                company_name,
                status,
                category,
                payment,
                comment,
                address,
                photo_path,
                "|".join(comment_photo_paths),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                session.get("company_id")
            ),
        )
        conn.commit()
        conn.close()
        return redirect("/clients")

    return render_template("client_form.html")


@clients_bp.route("/clients/<int:client_id>")
def client_detail(client_id):
    conn = get_db()

    client = conn.execute(
        "SELECT * FROM clients WHERE id = ? AND company_id = ?",
        (client_id, session.get("company_id"))
    ).fetchone()

    sales = conn.execute("""
        SELECT * FROM sales
        WHERE client_id = ?
        ORDER BY id DESC
    """, (client_id,)).fetchall()

    conn.close()

    if not client:
        return "Клиент не найден", 404

    return render_template(
        "client_detail.html",
        client=client,
        sales=sales
    )


@clients_bp.route("/clients/<int:client_id>/add_item", methods=["POST"])
def add_item(client_id):
    conn = get_db()

    item_id = request.form.get("item_id")
    payment_method = request.form.get("payment_method", "Не оплачено")

    item = conn.execute(
        "SELECT * FROM items WHERE id = ?",
        (item_id,)
    ).fetchone()

    if item:
        conn.execute("""
            INSERT INTO client_items (client_id, item_id, price, payment_method, is_paid, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            client_id,
            item_id,
            item["price"],
            payment_method,
            0,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

    conn.close()
    return "", 200
    
@clients_bp.route("/api/client/<int:client_id>")
def api_client(client_id):
    conn = get_db()

    client = conn.execute(
        "SELECT * FROM clients WHERE id = ?",
        (client_id,)
    ).fetchone()

    deals = conn.execute("""
        SELECT * FROM sales
        WHERE client_id = ?
        ORDER BY id DESC
    """, (client_id,)).fetchall()

    # 🔥 ВАЖНО: сначала берём services
    items = conn.execute(
        "SELECT * FROM items"
    ).fetchall()

    # ❗ И ТОЛЬКО ПОТОМ закрываем
    conn.close()

    return {
        "client": dict(client) if client else {},
        "deals": [dict(d) for d in deals],
        "items": [dict(i) for i in items]
    }
    
@clients_bp.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    conn = get_db()

    if request.method == "POST":
        old_client = conn.execute(
            "SELECT * FROM clients WHERE id = ?",
            (client_id,)
        ).fetchone()

        photo_path = old_client["photo"] if old_client and "photo" in old_client.keys() else ""
        old_comment_photos = old_client["comment_photos"] if old_client and "comment_photos" in old_client.keys() else ""
        comment_photo_paths = old_comment_photos.split("|") if old_comment_photos else []

        photo = request.files.get("photo")
        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            save_path = os.path.join(UPLOAD_DIR, filename)
            photo.save(save_path)
            photo_path = "/" + save_path.replace("\\", "/")

        comment_photos = request.files.getlist("comment_photos")
        for file in comment_photos:
            if file and file.filename:
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                save_path = os.path.join(COMMENT_UPLOAD_DIR, filename)
                file.save(save_path)
                comment_photo_paths.append("/" + save_path.replace("\\", "/"))

        conn.execute("""
            UPDATE clients
            SET full_name = ?, phone = ?, iin = ?, company_name = ?, status = ?,
                category = ?, payment = ?, comment = ?, address = ?, photo = ?, comment_photos = ?
            WHERE id = ?
        """, (
            request.form["full_name"],
            request.form.get("phone", ""),
            request.form.get("iin", ""),
            request.form.get("company_name", ""),
            request.form.get("status", ""),
            request.form.get("category", ""),
            request.form.get("payment", ""),
            request.form.get("comment", ""),
            request.form.get("address", ""),
            photo_path,
            "|".join([p for p in comment_photo_paths if p]),
            client_id
        ))

        conn.commit()
        conn.close()
        return {"status": "ok"}

    client = conn.execute(
        "SELECT * FROM clients WHERE id = ?",
        (client_id,)
    ).fetchone()

    conn.close()

    if not client:
        return "Клиент не найден", 404

    return render_template("client_edit.html", client=client)
    
@clients_bp.route("/clients/<int:client_id>/delete")
def delete_client(client_id):
    conn = get_db()

    conn.execute(
        "UPDATE clients SET is_deleted = 1 WHERE id = ?",
        (client_id,)
    )

    conn.commit()
    conn.close()

    return redirect("/clients")
    
@clients_bp.route("/clients/deleted")
def deleted_clients():
    conn = get_db()
    data = conn.execute(
        "SELECT * FROM clients WHERE is_deleted = 1 ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("clients_deleted.html", clients=data)
    
@clients_bp.route("/clients/<int:client_id>/restore")
def restore_client(client_id):
    conn = get_db()
    
    conn.execute(
        "UPDATE clients SET is_deleted = 0 WHERE id = ?",
        (client_id,)
    )
    
    conn.commit()
    conn.close()
    
    return redirect("/clients/deleted")
    
@clients_bp.route("/clients/<int:client_id>/delete_permanently")
def delete_client_permanently(client_id):
    conn = get_db()

    conn.execute(
        "DELETE FROM clients WHERE id = ?",
        (client_id,)
    )

    conn.commit()
    conn.close()

    return redirect("/clients/deleted")
    
@clients_bp.route("/api/clients")
def api_clients():
    conn = get_db()

    clients = conn.execute("""
        SELECT 
            id,
            full_name,
            phone,
            iin,
            company_name,
            address
        FROM clients
        WHERE is_deleted = 0 AND company_id = ?
        ORDER BY id DESC
    """, (session.get("company_id"),)).fetchall()

    conn.close()

    return [dict(c) for c in clients]
    
@clients_bp.route("/api/client/<int:id>/sales")
def client_sales(id):
    conn = get_db()

    sales = conn.execute("""
        SELECT * FROM sales
        WHERE client_id = ?
        ORDER BY id DESC
    """, (id,)).fetchall()

    conn.close()

    return [dict(s) for s in sales]