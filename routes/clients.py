from datetime import datetime, timedelta
import os

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from models import get_db, pool
from utils.timezone import now_kz


UPLOAD_DIR = os.path.join("static", "uploads", "clients")
COMMENT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "comments")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(COMMENT_UPLOAD_DIR, exist_ok=True)

clients_bp = Blueprint("clients", __name__)


def format_date_ru(date_value):
    if not date_value:
        return ""

    if hasattr(date_value, "strftime"):
        return date_value.strftime("%d.%m.%Y")

    try:
        return datetime.strptime(str(date_value), "%Y-%m-%d").strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(date_value)


def _company_id():
    return session.get("company_id")


def _save_uploaded_file(file_storage, folder, with_microseconds=False):
    if not file_storage or not file_storage.filename:
        return ""

    safe_name = secure_filename(file_storage.filename)
    if not safe_name:
        return ""

    date_format = "%Y%m%d%H%M%S%f" if with_microseconds else "%Y%m%d%H%M%S"
    filename = f"{now_kz().strftime(date_format)}_{safe_name}"
    save_path = os.path.join(folder, filename)
    file_storage.save(save_path)

    return "/" + save_path.replace("\\", "/")


def _serialize_value(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value


def _serialize_row(row):
    if not row:
        return {}
    return {key: _serialize_value(value) for key, value in dict(row).items()}


@clients_bp.route("/clients")
def clients():
    company_id = _company_id()
    search = request.args.get("search", "").strip()

    conn = get_db()
    try:
        cur = conn.cursor()

        search_condition = ""
        params = [company_id]

        if search:
            search_condition = """
                AND (
                    COALESCE(full_name, '') ILIKE %s
                    OR COALESCE(phone, '') ILIKE %s
                    OR COALESCE(company_name, '') ILIKE %s
                    OR COALESCE(iin, '') ILIKE %s
                )
            """
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern, pattern])

        cur.execute(
            f"""
            SELECT *
            FROM clients
            WHERE company_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
              {search_condition}
            ORDER BY id DESC
            """,
            tuple(params),
        )
        active_clients = cur.fetchall()

        deleted_params = [company_id]
        if search:
            deleted_params.extend([pattern, pattern, pattern, pattern])

        cur.execute(
            f"""
            SELECT *
            FROM clients
            WHERE company_id = %s
              AND COALESCE(is_deleted, FALSE) = TRUE
              {search_condition}
            ORDER BY id DESC
            """,
            tuple(deleted_params),
        )
        deleted_clients = cur.fetchall()

        return render_template(
            "clients.html",
            clients=active_clients,
            deleted_clients=deleted_clients,
            search=search,
        )
    finally:
        pool.putconn(conn)


@clients_bp.route("/clients/add", methods=["POST"])
def add_client():
    company_id = _company_id()

    full_name = request.form.get("full_name", "").strip()
    if not full_name:
        return jsonify({"status": "error", "message": "Укажите имя клиента"}), 400

    photo_path = _save_uploaded_file(request.files.get("photo"), UPLOAD_DIR)

    comment_photo_paths = []
    for file_storage in request.files.getlist("comment_photos"):
        path = _save_uploaded_file(
            file_storage,
            COMMENT_UPLOAD_DIR,
            with_microseconds=True,
        )
        if path:
            comment_photo_paths.append(path)

    conn = get_db()
    try:
        cur = conn.cursor()
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
                company_id,
                is_deleted
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, NULLIF(%s, '')::date, %s, %s, %s, %s, FALSE
            )
            RETURNING id
            """,
            (
                full_name,
                request.form.get("phone", "").strip(),
                request.form.get("iin", "").strip(),
                request.form.get("company_name", "").strip(),
                request.form.get("status", "Новый").strip() or "Новый",
                request.form.get("category", "").strip(),
                request.form.get("payment", "Не оплачено").strip() or "Не оплачено",
                request.form.get("comment", "").strip(),
                request.form.get("address", "").strip(),
                request.form.get("contract_number", "").strip(),
                request.form.get("contract_date", "").strip(),
                photo_path,
                "|".join(comment_photo_paths),
                now_kz(),
                company_id,
            ),
        )
        client_id = cur.fetchone()["id"]
        conn.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "ok", "id": client_id})

        return redirect(url_for("clients.clients"))
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@clients_bp.route("/clients/<int:client_id>")
def client_detail(client_id):
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM clients
            WHERE id = %s AND company_id = %s
            """,
            (client_id, company_id),
        )
        client = cur.fetchone()

        if not client:
            return "Клиент не найден", 404

        cur.execute(
            """
            SELECT *
            FROM sales
            WHERE client_id = %s AND company_id = %s
            ORDER BY id DESC
            """,
            (client_id, company_id),
        )
        sales = cur.fetchall()

        formatted_sales = []
        for sale in sales:
            new_sale = dict(sale)
            created_at = sale.get("created_at") if hasattr(sale, "get") else sale["created_at"]

            try:
                new_sale["date_str"] = (created_at + timedelta(hours=5)).strftime(
                    "%d.%m.%Y %H:%M"
                )
            except (TypeError, AttributeError):
                new_sale["date_str"] = str(created_at or "")

            formatted_sales.append(new_sale)

        return render_template(
            "client_detail.html",
            client=client,
            sales=formatted_sales,
        )
    finally:
        pool.putconn(conn)


@clients_bp.route("/clients/<int:client_id>/add_item", methods=["POST"])
def add_item(client_id):
    company_id = _company_id()
    item_id = request.form.get("item_id", type=int)
    payment_method = request.form.get("payment_method", "Не оплачено")

    if not item_id:
        return jsonify({"status": "error", "message": "Товар не выбран"}), 400

    conn = get_db()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id
            FROM clients
            WHERE id = %s AND company_id = %s
            """,
            (client_id, company_id),
        )
        if not cur.fetchone():
            return jsonify({"status": "error", "message": "Клиент не найден"}), 404

        cur.execute(
            """
            SELECT *
            FROM items
            WHERE id = %s AND company_id = %s
            """,
            (item_id, company_id),
        )
        item = cur.fetchone()

        if not item:
            return jsonify({"status": "error", "message": "Товар не найден"}), 404

        cur.execute(
            """
            INSERT INTO client_items (
                client_id,
                item_id,
                price,
                payment_method,
                is_paid,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                client_id,
                item_id,
                item["price"],
                payment_method,
                0,
                now_kz(),
            ),
        )
        conn.commit()

        return jsonify({"status": "ok"})
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@clients_bp.route("/api/client/<int:client_id>")
def api_client(client_id):
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM clients
            WHERE id = %s AND company_id = %s
            """,
            (client_id, company_id),
        )
        client = cur.fetchone()

        if not client:
            return jsonify({"status": "error", "message": "Клиент не найден"}), 404

        cur.execute(
            """
            SELECT *
            FROM sales
            WHERE client_id = %s AND company_id = %s
            ORDER BY id DESC
            """,
            (client_id, company_id),
        )
        deals = cur.fetchall()

        cur.execute(
            """
            SELECT *
            FROM items
            WHERE company_id = %s
            ORDER BY id DESC
            """,
            (company_id,),
        )
        items = cur.fetchall()

        return jsonify(
            {
                "client": _serialize_row(client),
                "deals": [_serialize_row(row) for row in deals],
                "items": [_serialize_row(row) for row in items],
            }
        )
    finally:
        pool.putconn(conn)


@clients_bp.route("/clients/<int:client_id>/edit", methods=["POST"])
def edit_client(client_id):
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM clients
            WHERE id = %s AND company_id = %s
            """,
            (client_id, company_id),
        )
        old_client = cur.fetchone()

        if not old_client:
            return jsonify({"status": "error", "message": "Клиент не найден"}), 404

        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            return jsonify({"status": "error", "message": "Укажите имя клиента"}), 400

        photo_path = old_client["photo"] or ""
        new_photo_path = _save_uploaded_file(request.files.get("photo"), UPLOAD_DIR)
        if new_photo_path:
            photo_path = new_photo_path

        old_comment_photos = old_client["comment_photos"] or ""
        comment_photo_paths = [
            path for path in old_comment_photos.split("|") if path
        ]

        for file_storage in request.files.getlist("comment_photos"):
            path = _save_uploaded_file(
                file_storage,
                COMMENT_UPLOAD_DIR,
                with_microseconds=True,
            )
            if path:
                comment_photo_paths.append(path)

        cur.execute(
            """
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
                contract_date = NULLIF(%s, '')::date,
                photo = %s,
                comment_photos = %s
            WHERE id = %s AND company_id = %s
            """,
            (
                full_name,
                request.form.get("phone", "").strip(),
                request.form.get("iin", "").strip(),
                request.form.get("company_name", "").strip(),
                request.form.get("status", "Новый").strip() or "Новый",
                request.form.get("category", "").strip(),
                request.form.get("payment", "Не оплачено").strip() or "Не оплачено",
                request.form.get("comment", "").strip(),
                request.form.get("address", "").strip(),
                request.form.get("contract_number", "").strip(),
                request.form.get("contract_date", "").strip(),
                photo_path,
                "|".join(comment_photo_paths),
                client_id,
                company_id,
            ),
        )
        conn.commit()

        return jsonify({"status": "ok"})
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@clients_bp.route("/clients/<int:client_id>/delete", methods=["POST", "GET"])
def delete_client(client_id):
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE clients
            SET is_deleted = TRUE
            WHERE id = %s AND company_id = %s
            """,
            (client_id, company_id),
        )
        conn.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "ok"})

        return redirect(url_for("clients.clients"))
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@clients_bp.route("/clients/deleted")
def deleted_clients():
    return redirect(url_for("clients.clients", tab="deleted"))


@clients_bp.route("/clients/<int:client_id>/restore", methods=["POST", "GET"])
def restore_client(client_id):
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE clients
            SET is_deleted = FALSE
            WHERE id = %s AND company_id = %s
            """,
            (client_id, company_id),
        )
        conn.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "ok"})

        return redirect(url_for("clients.clients", tab="deleted"))
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@clients_bp.route(
    "/clients/<int:client_id>/delete_permanently",
    methods=["POST", "GET"],
)
def delete_client_permanently(client_id):
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM clients
            WHERE id = %s
              AND company_id = %s
              AND COALESCE(is_deleted, FALSE) = TRUE
            """,
            (client_id, company_id),
        )
        conn.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "ok"})

        return redirect(url_for("clients.clients", tab="deleted"))
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@clients_bp.route("/api/clients")
def api_clients():
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                full_name,
                phone,
                iin,
                company_name,
                address
            FROM clients
            WHERE COALESCE(is_deleted, FALSE) = FALSE
              AND company_id = %s
            ORDER BY id DESC
            """,
            (company_id,),
        )
        rows = cur.fetchall()
        return jsonify([_serialize_row(row) for row in rows])
    finally:
        pool.putconn(conn)


@clients_bp.route("/api/client/<int:client_id>/sales")
def client_sales(client_id):
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM sales
            WHERE client_id = %s AND company_id = %s
            ORDER BY id DESC
            """,
            (client_id, company_id),
        )
        rows = cur.fetchall()
        return jsonify([_serialize_row(row) for row in rows])
    finally:
        pool.putconn(conn)


@clients_bp.route("/api/clients/create", methods=["POST"])
def api_create_client():
    data = request.get_json(silent=True) or {}
    company_id = _company_id()

    full_name = str(data.get("full_name", "")).strip()
    if not full_name:
        return jsonify({"success": False, "message": "Укажите имя клиента"}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO clients (
                full_name,
                phone,
                iin,
                company_name,
                address,
                comment,
                status,
                payment,
                created_at,
                company_id,
                is_deleted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            RETURNING id
            """,
            (
                full_name,
                str(data.get("phone", "")).strip(),
                str(data.get("iin", "")).strip(),
                str(data.get("company_name", "")).strip(),
                str(data.get("address", "")).strip(),
                str(data.get("comment", "")).strip(),
                str(data.get("status", "Новый")).strip() or "Новый",
                str(data.get("payment", "Не оплачено")).strip() or "Не оплачено",
                now_kz(),
                company_id,
            ),
        )
        client_id = cur.fetchone()["id"]
        conn.commit()

        return jsonify({"success": True, "id": client_id})
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@clients_bp.route("/api/clients/by-iin/<iin>")
def get_client_by_iin(iin):
    company_id = _company_id()
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM clients
            WHERE company_id = %s
              AND iin = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (company_id, iin),
        )
        client = cur.fetchone()

        if client:
            return jsonify({"found": True, "client": _serialize_row(client)})

        return jsonify({"found": False})
    finally:
        pool.putconn(conn)