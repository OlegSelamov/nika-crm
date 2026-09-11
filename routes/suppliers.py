from datetime import datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, session

from models import get_db, pool
from routes.expenses import upsert_expense_from_source, _sync_expense_to_accounting
from routes.stock import is_product


suppliers_bp = Blueprint("suppliers", __name__)


def ensure_supplier_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            bin_iin TEXT,
            contact_name TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            comment TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_company ON suppliers(company_id)")
    cur.execute("ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS supplier_id INTEGER")
    conn.commit()
    cur.close()


def _supplier_for_company(cur, supplier_id, company_id):
    if not supplier_id:
        return None
    cur.execute("""
        SELECT *
        FROM suppliers
        WHERE id = %s AND company_id = %s AND is_active = TRUE
    """, (supplier_id, company_id))
    return cur.fetchone()


@suppliers_bp.route("/suppliers")
def suppliers_page():
    company_id = session.get("company_id")
    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                s.*,
                COUNT(sm.id) FILTER (WHERE sm.movement_type = 'income') AS income_count,
                COALESCE(SUM(sm.total) FILTER (WHERE sm.movement_type = 'income'), 0) AS income_total,
                MAX(sm.created_at) FILTER (WHERE sm.movement_type = 'income') AS last_income_at
            FROM suppliers s
            LEFT JOIN stock_movements sm
              ON sm.supplier_id = s.id
             AND sm.company_id = s.company_id
            WHERE s.company_id = %s
              AND s.is_active = TRUE
            GROUP BY s.id
            ORDER BY LOWER(s.name), s.id
        """, (company_id,))
        suppliers = cur.fetchall()
        return render_template("suppliers.html", suppliers=suppliers)
    finally:
        pool.putconn(conn)


@suppliers_bp.route("/api/suppliers", methods=["GET", "POST"])
def api_suppliers():
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()

        if request.method == "GET":
            cur.execute("""
                SELECT id, name, bin_iin, contact_name, phone, email, address, comment
                FROM suppliers
                WHERE company_id = %s AND is_active = TRUE
                ORDER BY LOWER(name), id
            """, (company_id,))
            return jsonify(cur.fetchall())

        data = request.get_json(silent=True) or request.form
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "error": "Укажите название поставщика"}), 400

        cur.execute("""
            INSERT INTO suppliers (
                company_id, name, bin_iin, contact_name, phone,
                email, address, comment, created_at, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
            RETURNING id
        """, (
            company_id,
            name,
            str(data.get("bin_iin") or "").strip() or None,
            str(data.get("contact_name") or "").strip() or None,
            str(data.get("phone") or "").strip() or None,
            str(data.get("email") or "").strip() or None,
            str(data.get("address") or "").strip() or None,
            str(data.get("comment") or "").strip() or None,
        ))
        supplier_id = cur.fetchone()["id"]
        conn.commit()
        return jsonify({"success": True, "id": supplier_id})
    finally:
        pool.putconn(conn)


@suppliers_bp.route("/api/suppliers/<int:supplier_id>", methods=["PUT", "DELETE"])
def api_supplier_detail(supplier_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()

        cur.execute(
            "SELECT id, name FROM suppliers WHERE id = %s AND company_id = %s",
            (supplier_id, company_id),
        )
        supplier = cur.fetchone()
        if not supplier:
            return jsonify({"success": False, "error": "Поставщик не найден"}), 404

        if request.method == "DELETE":
            # If this supplier has never been used, remove the row completely.
            # If there are historical stock movements, keep the row as archived
            # so old receipts/stock history continue to point to the same supplier.
            cur.execute("""
                SELECT COUNT(*) AS linked_count
                FROM stock_movements
                WHERE company_id = %s AND supplier_id = %s
            """, (company_id, supplier_id))
            linked_count = int(cur.fetchone()["linked_count"] or 0)

            if linked_count == 0:
                cur.execute(
                    "DELETE FROM suppliers WHERE id = %s AND company_id = %s",
                    (supplier_id, company_id),
                )
                action = "deleted"
            else:
                cur.execute("""
                    UPDATE suppliers
                    SET is_active = FALSE, updated_at = NOW()
                    WHERE id = %s AND company_id = %s
                """, (supplier_id, company_id))
                action = "archived"

            conn.commit()
            return jsonify({
                "success": True,
                "action": action,
                "linked_count": linked_count,
                "message": (
                    "Поставщик удалён"
                    if action == "deleted"
                    else "Поставщик скрыт из активных. История приходов сохранена"
                ),
            })

        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "error": "Укажите название поставщика"}), 400

        cur.execute("""
            UPDATE suppliers
            SET name=%s, bin_iin=%s, contact_name=%s, phone=%s,
                email=%s, address=%s, comment=%s, updated_at=NOW()
            WHERE id=%s AND company_id=%s
        """, (
            name,
            str(data.get("bin_iin") or "").strip() or None,
            str(data.get("contact_name") or "").strip() or None,
            str(data.get("phone") or "").strip() or None,
            str(data.get("email") or "").strip() or None,
            str(data.get("address") or "").strip() or None,
            str(data.get("comment") or "").strip() or None,
            supplier_id,
            company_id,
        ))
        conn.commit()
        return jsonify({"success": True})
    finally:
        pool.putconn(conn)


@suppliers_bp.route("/stock/income/supplier", methods=["POST"])
def stock_income_with_supplier():
    company_id = session.get("company_id")
    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()

        item_id = request.form.get("item_id")
        supplier_id = request.form.get("supplier_id")
        try:
            quantity = float(request.form.get("quantity", 0))
            price = float(request.form.get("price", 0))
        except (TypeError, ValueError):
            return "Некорректное количество или цена", 400

        if quantity <= 0 or price < 0:
            return "Проверьте количество и закупочную цену", 400

        if not is_product(cur, item_id, company_id):
            return "Приход доступен только для товаров", 400

        supplier = _supplier_for_company(cur, supplier_id, company_id)
        if not supplier:
            return "Выберите поставщика", 400

        cur.execute("SELECT name FROM items WHERE id = %s AND company_id = %s", (item_id, company_id))
        item_row = cur.fetchone()
        item_name = item_row["name"] if item_row else f"Товар #{item_id}"

        comment = request.form.get("comment")
        total = quantity * price
        movement_datetime = datetime.utcnow() + timedelta(hours=5)

        cur.execute("""
            INSERT INTO stock_movements (
                company_id, item_id, movement_type, quantity, price,
                total, comment, supplier_id, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            company_id, item_id, "income", quantity, price,
            total, comment, supplier["id"], movement_datetime
        ))
        movement_id = cur.fetchone()["id"]

        expense_id = upsert_expense_from_source(
            cur,
            company_id=company_id,
            source_type="stock_income",
            source_id=movement_id,
            category="Закупки",
            description=f"Закуп товара: {item_name} · {supplier['name']}",
            amount=total,
            expense_date=movement_datetime.date(),
            payment_method="Другое",
            comment=comment or f"Поставщик: {supplier['name']}",
            user_id=session.get("user_id"),
        )
        _sync_expense_to_accounting(cur, expense_id, company_id)
        conn.commit()
        return redirect("/stock/income")
    finally:
        pool.putconn(conn)
