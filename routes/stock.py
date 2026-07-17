from flask import Blueprint, render_template, request, redirect, session
from models import get_db, pool
from datetime import datetime
from flask import jsonify

stock_bp = Blueprint("stock", __name__)


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
            price,
            quantity * price,
            comment,
            datetime.now()
        ))

        conn.commit()

        return redirect("/stock/income")

    cur.execute("""
        SELECT *
        FROM items
        WHERE company_id = %s
        ORDER BY name
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

        LEFT JOIN items
        ON items.id = stock_movements.item_id

        WHERE stock_movements.company_id = %s

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
            "writeoff",
            quantity,
            0,
            0,
            comment,
            datetime.now()
        ))

        conn.commit()

        return redirect("/stock/writeoff")

    cur.execute("""
        SELECT *
        FROM items
        WHERE company_id = %s
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

        LEFT JOIN items
        ON items.id = stock_movements.item_id

        WHERE stock_movements.company_id = %s

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
    """, (
        session.get("company_id"),
        data["item_id"],
        "income",
        data["quantity"],
        data["price"],
        data["quantity"] * data["price"],
        data.get("comment",""),
        datetime.now()
    ))

    conn.commit()

    pool.putconn(conn)

    return jsonify({
        "success": True
    })
    
@stock_bp.route(
    "/api/stock/writeoff",
    methods=["POST"]
)
def api_stock_writeoff():

    data = request.json

    conn = get_db()
    cur = conn.cursor()

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
    """, (
        session.get("company_id"),
        data["item_id"],
        "writeoff",
        data["quantity"],
        0,
        0,
        data.get("comment",""),
        datetime.now()
    ))

    conn.commit()

    pool.putconn(conn)

    return jsonify({
        "success": True
    })