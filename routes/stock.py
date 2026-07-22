from flask import Blueprint, render_template, request, redirect, session
from models import get_db, pool
from datetime import datetime, timedelta
from flask import jsonify
from utils.timezone import now_kz
from routes.expenses import upsert_expense_from_source, _sync_expense_to_accounting

stock_bp = Blueprint("stock", __name__)


def is_product(cur, item_id, company_id):
    cur.execute("""
        SELECT 1
        FROM items
        WHERE id = %s
          AND company_id = %s
          AND COALESCE(item_type, 'product') = 'product'
    """, (item_id, company_id))
    return cur.fetchone() is not None


@stock_bp.route("/stock/income", methods=["GET", "POST"])
def stock_income():

    conn = get_db()
    
    cur = conn.cursor()

    if request.method == "POST":

        item_id = request.form.get("item_id")

        quantity = float(
            request.form.get("quantity", 0)
        )

        price = float(
            request.form.get("price", 0)
        )

        comment = request.form.get("comment")
        company_id = session.get("company_id")

        if not is_product(cur, item_id, company_id):
            pool.putconn(conn)
            return "Приход доступен только для товаров", 400

        cur.execute("""
            SELECT name
            FROM items
            WHERE id = %s AND company_id = %s
        """, (item_id, company_id))
        item_row = cur.fetchone()

        item_name = item_row["name"] if item_row else f"Товар #{item_id}"
        total = quantity * price
        movement_datetime = datetime.utcnow() + timedelta(hours=5)

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
            RETURNING id
        """, (
            company_id,
            item_id,
            "income",
            quantity,
            price,
            total,
            comment,
            movement_datetime
        ))

        movement_id = cur.fetchone()["id"]

        expense_id = upsert_expense_from_source(
            cur,
            company_id=company_id,
            source_type="stock_income",
            source_id=movement_id,
            category="Закупки",
            description=f"Закуп товара: {item_name}",
            amount=total,
            expense_date=movement_datetime.date(),
            payment_method="Другое",
            comment=comment or "Создано автоматически из прихода товара",
            user_id=session.get("user_id"),
        )

        _sync_expense_to_accounting(cur, expense_id, company_id)

        conn.commit()
        pool.putconn(conn)

        return redirect("/stock/income")

    cur.execute("""
        SELECT
            items.*,

            COALESCE(
                SUM(
                    CASE
                        WHEN stock_movements.movement_type = 'income'
                            THEN stock_movements.quantity

                        WHEN stock_movements.movement_type = 'refund'
                            THEN stock_movements.quantity

                        WHEN stock_movements.movement_type = 'sale'
                            THEN -stock_movements.quantity

                        WHEN stock_movements.movement_type = 'writeoff'
                            THEN -stock_movements.quantity
                    END
                ),
                0
            ) AS stock

        FROM items

        LEFT JOIN stock_movements
            ON items.id = stock_movements.item_id

        WHERE items.company_id = %s
          AND COALESCE(items.item_type, 'product') = 'product'

        GROUP BY items.id

        ORDER BY items.name
    """, (
        session.get("company_id"),
    ))

    items = cur.fetchall()

    # Получаем последние приходы товара
    cur.execute("""
        SELECT
            stock_movements.*,
            items.name AS item_name

        FROM stock_movements

        LEFT JOIN items
            ON items.id = stock_movements.item_id

        WHERE
            stock_movements.company_id = %s
            AND stock_movements.movement_type = 'income'
            AND COALESCE(items.item_type, 'product') = 'product'

        ORDER BY stock_movements.id DESC

        LIMIT 30
    """, (
        session.get("company_id"),
    ))

    income_rows = cur.fetchall()

    pool.putconn(conn)

    return render_template(
        "stock_income.html",
        items=items,
        income_rows=income_rows
    )
    
@stock_bp.route("/stock")
def stock():

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        SELECT
            items.*,

            COALESCE(
                SUM(
                    CASE
                        WHEN stock_movements.movement_type='income'
                        THEN stock_movements.quantity
                        
                        WHEN stock_movements.movement_type='refund'
                        THEN stock_movements.quantity

                        WHEN stock_movements.movement_type='sale'
                        THEN -stock_movements.quantity

                        WHEN stock_movements.movement_type='writeoff'
                        THEN -stock_movements.quantity
                    END
                ),
                0
            ) as stock

        FROM items

        LEFT JOIN stock_movements
        ON items.id = stock_movements.item_id

        WHERE items.company_id = %s
          AND COALESCE(items.item_type, 'product') = 'product'

        GROUP BY items.id

        ORDER BY items.name
    """, (
        session.get("company_id"),
    ))
    
    items = cur.fetchall()

    pool.putconn(conn)

    return render_template(
        "stock.html",
        items=items
    )
    
@stock_bp.route("/stock/movements")
def stock_movements():

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        SELECT
            stock_movements.*,
            items.name as item_name

        FROM stock_movements

        JOIN items
          ON items.id = stock_movements.item_id
         AND items.company_id = stock_movements.company_id

        WHERE stock_movements.company_id = %s
          AND COALESCE(items.item_type, 'product') = 'product'

        ORDER BY stock_movements.id DESC
    """, (
        session.get("company_id"),
    ))
    
    rows = cur.fetchall()

    pool.putconn(conn)

    return render_template(
        "stock_movements.html",
        rows=rows
    )
    
@stock_bp.route("/stock/writeoff", methods=["GET", "POST"])
def stock_writeoff():

    conn = get_db()
    
    cur = conn.cursor()

    if request.method == "POST":

        item_id = request.form.get("item_id")

        quantity = float(
            request.form.get("quantity", 0)
        )

        comment = request.form.get("comment")
        company_id = session.get("company_id")

        if not is_product(cur, item_id, company_id):
            pool.putconn(conn)
            return "Списание доступен только для товаров", 400

        cur.execute("""
            SELECT
                name,
                COALESCE(purchase_price, 0) AS purchase_price
            FROM items
            WHERE id = %s AND company_id = %s
        """, (item_id, company_id))

        item_row = cur.fetchone()

        if not item_row:
            pool.putconn(conn)
            return "Товар не найден", 404

        purchase_price = float(item_row["purchase_price"] or 0)
        writeoff_total = quantity * purchase_price

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
            RETURNING id
        """, (
            company_id,
            item_id,
            "writeoff",
            quantity,
            purchase_price,
            writeoff_total,
            comment,
            datetime.utcnow() + timedelta(hours=5)
        ))

        movement_id = cur.fetchone()["id"]

        conn.commit()
        pool.putconn(conn)

        return redirect("/stock/writeoff")

    cur.execute("""
        SELECT
            items.*,

            COALESCE(
                SUM(
                    CASE
                        WHEN stock_movements.movement_type = 'income'
                            THEN stock_movements.quantity

                        WHEN stock_movements.movement_type = 'refund'
                            THEN stock_movements.quantity

                        WHEN stock_movements.movement_type = 'sale'
                            THEN -stock_movements.quantity

                        WHEN stock_movements.movement_type = 'writeoff'
                            THEN -stock_movements.quantity
                    END
                ),
                0
            ) AS stock

        FROM items

        LEFT JOIN stock_movements
            ON items.id = stock_movements.item_id

        WHERE items.company_id = %s
          AND COALESCE(items.item_type, 'product') = 'product'

        GROUP BY items.id

        ORDER BY items.name
    """, (
        session.get("company_id"),
    ))
    
    items = cur.fetchall()

    pool.putconn(conn)

    return render_template(
        "stock_writeoff.html",
        items=items
    )
    
@stock_bp.route("/api/stock")
def api_stock():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            items.*,

            COALESCE(
                SUM(
                    CASE
                        WHEN stock_movements.movement_type='income'
                        THEN stock_movements.quantity
                        
                        WHEN stock_movements.movement_type='refund'
                        THEN stock_movements.quantity

                        WHEN stock_movements.movement_type='sale'
                        THEN -stock_movements.quantity

                        WHEN stock_movements.movement_type='writeoff'
                        THEN -stock_movements.quantity
                    END
                ),
                0
            ) as stock

        FROM items

        LEFT JOIN stock_movements
        ON items.id = stock_movements.item_id

        WHERE items.company_id = %s
          AND COALESCE(items.item_type, 'product') = 'product'

        GROUP BY items.id

        ORDER BY items.name
    """, (
        session.get("company_id"),
    ))

    rows = cur.fetchall()

    pool.putconn(conn)

    return jsonify(rows)
    
@stock_bp.route("/api/stock/movements")
def api_stock_movements():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            stock_movements.*,
            items.name as item_name

        FROM stock_movements

        JOIN items
          ON items.id = stock_movements.item_id
         AND items.company_id = stock_movements.company_id

        WHERE stock_movements.company_id = %s
          AND COALESCE(items.item_type, 'product') = 'product'

        ORDER BY stock_movements.id DESC
    """, (
        session.get("company_id"),
    ))

    rows = cur.fetchall()

    pool.putconn(conn)

    return jsonify(rows)
    
@stock_bp.route(
    "/api/stock/income",
    methods=["POST"]
)
def api_stock_income():

    data = request.json

    conn = get_db()
    cur = conn.cursor()
    company_id = session.get("company_id")

    if not is_product(cur, data.get("item_id"), company_id):
        pool.putconn(conn)
        return jsonify({"success": False, "error": "Приход доступен только для товаров"}), 400

    quantity = float(data.get("quantity", 0))
    price = float(data.get("price", 0))
    total = quantity * price
    comment = data.get("comment", "")
    movement_datetime = datetime.utcnow() + timedelta(hours=5)

    cur.execute("""
        SELECT name
        FROM items
        WHERE id = %s AND company_id = %s
    """, (data["item_id"], company_id))
    item_row = cur.fetchone()
    item_name = item_row["name"] if item_row else f"Товар #{data['item_id']}"

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
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        company_id,
        data["item_id"],
        "income",
        quantity,
        price,
        total,
        comment,
        movement_datetime
    ))

    movement_id = cur.fetchone()["id"]

    expense_id = upsert_expense_from_source(
        cur,
        company_id=company_id,
        source_type="stock_income",
        source_id=movement_id,
        category="Закупки",
        description=f"Закуп товара: {item_name}",
        amount=total,
        expense_date=movement_datetime.date(),
        payment_method=data.get("payment_method") or "Другое",
        comment=comment or "Создано автоматически из прихода товара",
        user_id=session.get("user_id"),
    )

    _sync_expense_to_accounting(cur, expense_id, company_id)

    conn.commit()

    pool.putconn(conn)

    return jsonify({
        "success": True,
        "movement_id": movement_id,
        "expense_id": expense_id
    })
    
@stock_bp.route(
    "/api/stock/writeoff",
    methods=["POST"]
)
def api_stock_writeoff():

    data = request.json

    conn = get_db()
    cur = conn.cursor()
    company_id = session.get("company_id")

    if not is_product(cur, data.get("item_id"), company_id):
        pool.putconn(conn)
        return jsonify({
            "success": False,
            "error": "Списание доступно только для товаров"
        }), 400

    quantity = float(data.get("quantity", 0))

    cur.execute("""
        SELECT
            name,
            COALESCE(purchase_price, 0) AS purchase_price
        FROM items
        WHERE id = %s AND company_id = %s
    """, (
        data["item_id"],
        company_id
    ))

    item_row = cur.fetchone()

    if not item_row:
        pool.putconn(conn)
        return jsonify({
            "success": False,
            "error": "Товар не найден"
        }), 404

    purchase_price = float(item_row["purchase_price"] or 0)
    writeoff_total = quantity * purchase_price

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
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        company_id,
        data["item_id"],
        "writeoff",
        quantity,
        purchase_price,
        writeoff_total,
        data.get("comment", ""),
        datetime.utcnow() + timedelta(hours=5)
    ))

    movement_id = cur.fetchone()["id"]

    conn.commit()
    pool.putconn(conn)

    return jsonify({
        "success": True,
        "movement_id": movement_id,
        "price": purchase_price,
        "total": writeoff_total
    })
