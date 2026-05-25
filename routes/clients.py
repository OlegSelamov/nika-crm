from flask import Blueprint, render_template, request, redirect
from flask import session
from models import get_db
from datetime import datetime
from werkzeug.utils import secure_filename
import os

def format_date_ru(date_str):

    if not date_str:
        return ""

    try:
        return datetime.strptime(
            date_str,
            "%Y-%m-%d"
        ).strftime("%d.%m.%Y")

    except:
        return date_str

UPLOAD_DIR = os.path.join("static", "uploads", "clients")
COMMENT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "comments")

# создаём папки если их нет
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(COMMENT_UPLOAD_DIR, exist_ok=True)

clients_bp = Blueprint("clients", __name__)


@clients_bp.route("/clients")
def clients():
    conn = get_db()
    
    cur = conn.cursor()

    search = request.args.get("search", "").strip()

    if search:
        cur.execute("""
            SELECT * FROM clients
            WHERE company_id = %s
            AND (
                full_name LIKE %s
                OR phone LIKE %s
                OR company_name LIKE %s
                OR iin LIKE %s
            )
            ORDER BY id DESC
        """, (
            session.get("company_id"),
            f"%{search}%",
            f"%{search}%",
            f"%{search}%",
            f"%{search}%"
        ))
        
        clients = cur.fetchall()
    else:
        cur.execute("""
            SELECT * FROM clients
            WHERE company_id = %s
            ORDER BY id DESC
        """, (session.get("company_id"),))
        
        clients = cur.fetchall()

    pool.putconn(conn)

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
        
        cur = conn.cursor()
        
        print("CLIENT SAVE COMPANY:", session.get("company_id"))
        
        cur.execute(
            """
            INSERT INTO clients (
                full_name,
                phone,
                iin,
                company_name,
                status,
                category,
                payment,
                comment,
                address,
                contract_number,
                contract_date,
                photo,
                comment_photos,
                created_at,
                company_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                request.form.get("contract_number", ""),
                request.form.get("contract_date", ""),
                photo_path,
                "|".join(comment_photo_paths),
                datetime.now(),
                session.get("company_id")
            ),
        )
        conn.commit()
        pool.putconn(conn)
        return redirect("/clients")

    return render_template("client_form.html")


@clients_bp.route("/clients/<int:client_id>")
def client_detail(client_id):
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM clients WHERE id = %s AND company_id = %s",
        (client_id, session.get("company_id"))
    )
    
    client = cur.fetchone()

    cur.execute("""
        SELECT * FROM sales
        WHERE client_id = %s AND company_id = %s
        ORDER BY id DESC
    """, (client_id, session.get("company_id")))
    
    sales = cur.fetchall()

    pool.putconn(conn)

    if not client:
        return "Клиент не найден", 404

    formatted_sales = []

    for s in sales:
        try:
            dt = datetime.fromisoformat(s["created_at"])
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except:
            date_str = s["created_at"]

        new_s = dict(s)
        new_s["date_str"] = date_str

        formatted_sales.append(new_s)
        
    return render_template(
        "client_detail.html",
        client=client,
        sales=formatted_sales
    )


@clients_bp.route("/clients/<int:client_id>/add_item", methods=["POST"])
def add_item(client_id):
    conn = get_db()
    
    cur = conn.cursor()

    item_id = request.form.get("item_id")
    payment_method = request.form.get("payment_method", "Не оплачено")

    cur.execute(
        "SELECT * FROM items WHERE id = %s",
        (item_id,)
    )
    
    item = cur.fetchone()

    if item:
        cur.execute("""
            INSERT INTO client_items (client_id, item_id, price, payment_method, is_paid, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            client_id,
            item_id,
            item["price"],
            payment_method,
            0,
            datetime.now()
        ))
        conn.commit()

    pool.putconn(conn)
    return "", 200
    
@clients_bp.route("/api/client/<int:client_id>")
def api_client(client_id):
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM clients WHERE id = %s AND company_id = %s",
        (client_id, session.get("company_id"))
    )
    
    client = cur.fetchone()

    cur.execute("""
        SELECT * FROM sales
        WHERE client_id = %s AND company_id = %s
        ORDER BY id DESC
    """, (client_id, session.get("company_id")))
    
    deals = cur.fetchall()

    # 🔥 ВАЖНО: сначала берём services
    cur.execute(
        "SELECT * FROM items WHERE company_id = %s",
        (session.get("company_id"),)
    )
    
    items = cur.fetchall()

    # ❗ И ТОЛЬКО ПОТОМ закрываем
    pool.putconn(conn)

    return {
        "client": dict(client) if client else {},
        "deals": [dict(d) for d in deals],
        "items": [dict(i) for i in items]
    }
    
@clients_bp.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    conn = get_db()
    
    cur = conn.cursor()

    if request.method == "POST":

        cur.execute(
            "SELECT * FROM clients WHERE id = %s AND company_id = %s",
            (client_id, session.get("company_id"))
        )

        old_client = cur.fetchone()

        if not old_client:
            pool.putconn(conn)
            return "Нет доступа"

        photo_path = old_client["photo"] or ""
        old_comment_photos = old_client["comment_photos"] or ""
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

        cur.execute("""
            UPDATE clients
            SET full_name = %s, 
                phone = %s, 
                iin = %s, 
                company_name = %s, 
                status = %s,
                category = %s, 
                payment = %s, 
                comment = %s, 
                address = %s,
                contract_number = %s,
                contract_date = %s,
                photo = %s, 
                comment_photos = %s
            WHERE id = %s AND company_id = %s
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
            request.form.get("contract_number", ""),
            request.form.get("contract_date", ""),
            photo_path,
            "|".join([p for p in comment_photo_paths if p]),
            client_id,
            session.get("company_id")
        ))

        conn.commit()
        pool.putconn(conn)
        return {"status": "ok"}

    # GET
    cur.execute(
        "SELECT * FROM clients WHERE id = %s AND company_id = %s",
        (client_id, session.get("company_id"))
    )
    
    client = cur.fetchone()

    pool.putconn(conn)

    if not client:
        return "Клиент не найден", 404

    return render_template(
        "client_form.html",
        client=client
    )
    
@clients_bp.route("/clients/<int:client_id>/delete")
def delete_client(client_id):
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "UPDATE clients SET is_deleted = TRUE WHERE id = %s AND company_id = %s",
        (client_id, session.get("company_id"))
    )

    conn.commit()
    pool.putconn(conn)

    return redirect("/clients")
    
@clients_bp.route("/clients/deleted")
def deleted_clients():
    conn = get_db()
    
    cur = conn.cursor()
    
    cur.execute(
        "SELECT * FROM clients WHERE is_deleted = TRUE AND company_id = %s ORDER BY id DESC",
        (session.get("company_id"),)
    )
    
    data = cur.fetchall()
    pool.putconn(conn)
    return render_template("clients_deleted.html", clients=data)
    
@clients_bp.route("/clients/<int:client_id>/restore")
def restore_client(client_id):
    conn = get_db()
    
    cur = conn.cursor()
    
    cur.execute(
        "UPDATE clients SET is_deleted = FALSE WHERE id = %s AND company_id = %s",
        (client_id, session.get("company_id"))
    )
    
    conn.commit()
    pool.putconn(conn)
    
    return redirect("/clients/deleted")
    
@clients_bp.route("/clients/<int:client_id>/delete_permanently")
def delete_client_permanently(client_id):
    conn = get_db()
    
    cur = conn.cursor()

    (cur.execute(
        "DELETE FROM clients WHERE id = %s AND company_id = %s",
        (client_id, session.get("company_id"))
    ))

    conn.commit()
    pool.putconn(conn)

    return redirect("/clients/deleted")
    
@clients_bp.route("/api/clients")
def api_clients():
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            id,
            full_name,
            phone,
            iin,
            company_name,
            address
        FROM clients
        WHERE is_deleted = FALSE AND company_id = %s
        ORDER BY id DESC
    """, (session.get("company_id"),))
    
    clients = cur.fetchall()

    pool.putconn(conn)

    return [dict(c) for c in clients]
    
@clients_bp.route("/api/client/<int:id>/sales")
def client_sales(id):
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM sales
        WHERE client_id = %s AND company_id = %s
        ORDER BY id DESC
    """, (id, session.get("company_id")))
    
    sales = cur.fetchall()

    pool.putconn(conn)

    return [dict(s) for s in sales]