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
        income_rows=income_rows
    )
    
@stock_bp.route("/stock")
def stock():
    company_id = session.get("company_id")
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        WITH stock_rows AS (
            SELECT
                i.*,
                COALESCE(SUM(
                    CASE
                        WHEN sm.movement_type IN ('income', 'refund') THEN sm.quantity
                        WHEN sm.movement_type IN ('sale', 'writeoff') THEN -sm.quantity
                        ELSE 0
                    END
                ), 0) AS stock
            FROM items i
            LEFT JOIN stock_movements sm
                ON i.id = sm.item_id
               AND i.company_id = sm.company_id
            WHERE i.company_id = %s
              AND COALESCE(i.item_type, 'product') = 'product'
            GROUP BY i.id
        )
        SELECT *
        FROM stock_rows
        ORDER BY LOWER(COALESCE(name, '')), id
        LIMIT 50
    """, (company_id,))
    items = cur.fetchall()

    cur.execute("""
        WITH stock_rows AS (
            SELECT
                i.id,
                COALESCE(i.purchase_price, 0) AS purchase_price,
                COALESCE(i.retail_price, 0) AS retail_price,
                COALESCE(SUM(
                    CASE
                        WHEN sm.movement_type IN ('income', 'refund') THEN sm.quantity
                        WHEN sm.movement_type IN ('sale', 'writeoff') THEN -sm.quantity
                        ELSE 0
                    END
                ), 0) AS stock
            FROM items i
            LEFT JOIN stock_movements sm
                ON i.id = sm.item_id
               AND i.company_id = sm.company_id
            WHERE i.company_id = %s
              AND COALESCE(i.item_type, 'product') = 'product'
            GROUP BY i.id
        )
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE stock > 5) AS normal,
            COUNT(*) FILTER (WHERE stock > 0 AND stock <= 5) AS low,
            COUNT(*) FILTER (WHERE stock <= 0) AS out,
            COALESCE(SUM(stock * purchase_price), 0) AS purchase_sum,
            COALESCE(SUM(stock * retail_price), 0) AS retail_sum
        FROM stock_rows
    """, (company_id,))
    stock_stats = cur.fetchone()

    cur.execute("""
        SELECT DISTINCT category
        FROM items
        WHERE company_id = %s
          AND COALESCE(item_type, 'product') = 'product'
          AND NULLIF(TRIM(category), '') IS NOT NULL
        ORDER BY category
    """, (company_id,))
    categories = [row["category"] for row in cur.fetchall()]

    pool.putconn(conn)

    return render_template(
        "stock.html",
        items=items,
        stock_stats=stock_stats,
        categories=categories,
        page_size=50
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

    pool.putconn(conn)

    return render_template("stock_writeoff.html")
    
@stock_bp.route("/api/stock")
def api_stock():
    company_id = session.get("company_id")
    legacy_mode = not bool(request.args)
    query = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    status = (request.args.get("status") or "all").strip().lower()
    sort = (request.args.get("sort") or "name").strip().lower()

    if legacy_mode:
        limit, offset = 1000000, 0
    else:
        try:
            limit = min(max(int(request.args.get("limit", 50)), 1), 100)
            offset = max(int(request.args.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0

    order_by = {
        "name": "LOWER(COALESCE(name, '')) ASC, id ASC",
        "stock-asc": "stock ASC, LOWER(COALESCE(name, '')) ASC",
        "stock-desc": "stock DESC, LOWER(COALESCE(name, '')) ASC",
        "retail-desc": "COALESCE(retail_price, 0) DESC, LOWER(COALESCE(name, '')) ASC",
        "retail-asc": "COALESCE(retail_price, 0) ASC, LOWER(COALESCE(name, '')) ASC",
    }.get(sort, "LOWER(COALESCE(name, '')) ASC, id ASC")

    where_parts = []
    params = [company_id]

    if query:
        where_parts.append("""
            (
                COALESCE(name, '') ILIKE %s OR
                COALESCE(category, '') ILIKE %s OR
                COALESCE(unit, '') ILIKE %s OR
                COALESCE(barcode, '') ILIKE %s OR
                COALESCE(gtin, '') ILIKE %s OR
                COALESCE(ntin, '') ILIKE %s
            )
        """)
        pattern = f"%{query}%"
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

    if category:
        where_parts.append("LOWER(COALESCE(category, '')) = LOWER(%s)")
        params.append(category)

    if status == "normal":
        where_parts.append("stock > 5")
    elif status == "low":
        where_parts.append("stock > 0 AND stock <= 5")
    elif status == "out":
        where_parts.append("stock <= 0")

    filtered_where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    conn = get_db()
    cur = conn.cursor()

    sql = f"""
        WITH stock_rows AS (
            SELECT
                i.*,
                COALESCE(SUM(
                    CASE
                        WHEN sm.movement_type IN ('income', 'refund') THEN sm.quantity
                        WHEN sm.movement_type IN ('sale', 'writeoff') THEN -sm.quantity
                        ELSE 0
                    END
                ), 0) AS stock
            FROM items i
            LEFT JOIN stock_movements sm
                ON i.id = sm.item_id
               AND i.company_id = sm.company_id
            WHERE i.company_id = %s
              AND COALESCE(i.item_type, 'product') = 'product'
            GROUP BY i.id
        ), filtered_rows AS (
            SELECT *
            FROM stock_rows
            {filtered_where}
        )
        SELECT *, COUNT(*) OVER() AS filtered_total
        FROM filtered_rows
        ORDER BY {order_by}
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    cur.execute(sql, params)

    rows = cur.fetchall()
    pool.putconn(conn)

    total = int(rows[0]["filtered_total"]) if rows else 0
    clean_rows = []
    for row in rows:
        item = dict(row)
        item.pop("filtered_total", None)
        clean_rows.append(item)

    if legacy_mode:
        return jsonify(clean_rows)

    return jsonify({
        "items": clean_rows,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(clean_rows) < total
    })
    
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
