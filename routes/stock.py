from flask import Blueprint, render_template, request, redirect, session
from models import get_db, pool
from datetime import datetime

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

    pool.putconn(conn)

    return render_template(
        "stock_income.html",
        items=items
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